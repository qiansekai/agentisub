package main

import (
	"bufio"
	"embed"
	"encoding/json"
	"flag"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

//go:embed all:dist
var distFS embed.FS

// agentisub M1 Go 服务层：静态 UI + Range 视频/音频 + 状态 API + tags/patches + git diff + 导出
// 状态文件：state/blocks.jsonl（唯一真源，原子写）

var root = flag.String("root", `D:\Kita-Tools\Media\agentisub`, "项目根目录")

type Block struct {
	ID         string            `json:"id"`
	Start      float64           `json:"start"`
	End        float64           `json:"end"`
	Kind       string            `json:"kind"`
	Song       string            `json:"song"`
	Ja         string            `json:"ja"`
	Zh         string            `json:"zh"`
	Confidence string            `json:"confidence"`
	Evidence   map[string]string `json:"evidence"`
	Tags       []string          `json:"tags"`
	History    []map[string]any  `json:"history"`
	Locked     bool              `json:"locked"`
}

type Tag struct {
	ID      string  `json:"id"`
	Type    string  `json:"type"` // retime|relisten|retranslate|lyrics|text|split|confirm
	Note    string  `json:"note"`
	BlockID string  `json:"block_id,omitempty"`
	Start   float64 `json:"start,omitempty"`
	End     float64 `json:"end,omitempty"`
	Status  string  `json:"status"` // open|processing|done|rejected
	Reply   string  `json:"reply,omitempty"`
	Created string  `json:"created"`
}

type Patch struct {
	ID      string         `json:"id"`
	BlockID string         `json:"block_id"`
	Changes map[string]any `json:"changes"`
	Reply   string         `json:"reply,omitempty"`
	TagID   string         `json:"tag_id,omitempty"`
}

type Store struct {
	mu     sync.Mutex
	blocks map[string]*Block
	order  []string
	tags   map[string]*Tag
	dirty  bool
}

func (s *Store) load() error {
	s.blocks = map[string]*Block{}
	s.order = nil
	s.tags = map[string]*Tag{}
	f, err := os.Open(filepath.Join(*root, "state", "blocks.jsonl"))
	if err != nil {
		return err
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		var b Block
		if err := json.Unmarshal([]byte(line), &b); err != nil {
			log.Printf("skip bad line: %v", err)
			continue
		}
		s.blocks[b.ID] = &b
		s.order = append(s.order, b.ID)
	}
	sort.Slice(s.order, func(i, j int) bool {
		return s.blocks[s.order[i]].Start < s.blocks[s.order[j]].Start
	})
	// tags
	if data, err := os.ReadFile(filepath.Join(*root, "state", "tags.json")); err == nil {
		var tags []*Tag
		if json.Unmarshal(data, &tags) == nil {
			for _, t := range tags {
				s.tags[t.ID] = t
			}
		}
	}
	log.Printf("[store] loaded %d blocks, %d tags", len(s.blocks), len(s.tags))
	return nil
}

func (s *Store) save() error {
	tmp := filepath.Join(*root, "state", "blocks.jsonl.tmp")
	f, err := os.Create(tmp)
	if err != nil {
		return err
	}
	for _, id := range s.order {
		data, _ := json.Marshal(s.blocks[id])
		fmt.Fprintln(f, string(data))
	}
	f.Close()
	if err := os.Rename(tmp, filepath.Join(*root, "state", "blocks.jsonl")); err != nil {
		return err
	}
	// tags
	tags := make([]*Tag, 0, len(s.tags))
	for _, t := range s.tags {
		tags = append(tags, t)
	}
	sort.Slice(tags, func(i, j int) bool { return tags[i].Created < tags[j].Created })
	data, _ := json.MarshalIndent(tags, "", "  ")
	os.WriteFile(filepath.Join(*root, "state", "tags.json"), data, 0o644)
	return nil
}

func (s *Store) commit() {
	if !s.dirty {
		return
	}
	s.dirty = false
	cmd := exec.Command("git", "-C", *root, "add", "state/")
	cmd.Run()
	cmd = exec.Command("git", "-C", *root, "commit", "-m", "[ui] checkpoint "+time.Now().Format("15:04:05"))
	if out, err := cmd.CombinedOutput(); err != nil {
		log.Printf("[git] commit: %v %s", err, strings.TrimSpace(string(out)))
	} else {
		log.Printf("[git] committed")
	}
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(v)
}

func main() {
	flag.Parse()
	st := &Store{}
	if err := st.load(); err != nil {
		log.Fatalf("load state: %v", err)
	}
	mux := http.NewServeMux()

	// ---- 静态 ----
	dist := filepath.Join(*root, "web", "dist")
	webdir := filepath.Join(*root, "web")
	if _, err := os.Stat(dist); err == nil {
		// 文件系统 dist（dev/build 迭代）
		mux.Handle("/", http.FileServer(http.Dir(dist)))
	} else if sub, err := fs.Sub(distFS, "dist"); err == nil {
		// go:embed 内嵌 dist（单二进制交付）
		mux.Handle("/", http.FileServer(http.FS(sub)))
	} else {
		mux.Handle("/", http.FileServer(http.Dir(webdir)))
	}

	// ---- 媒体（Range 由 ServeFile 处理）----
	// 视频路径从 state/meta.json 读取(media.video), 支持轻量代理切换; 缺省 proxy.mp4
	videoPath := filepath.Join(*root, "media", "proxy.mp4")
	if data, err := os.ReadFile(filepath.Join(*root, "state", "meta.json")); err == nil {
		var mm struct {
			Media struct {
				Video string `json:"video"`
			} `json:"media"`
		}
		if json.Unmarshal(data, &mm) == nil && mm.Media.Video != "" {
			videoPath = mm.Media.Video
		}
	}
	log.Printf("[video] serving %s", videoPath)
	mux.HandleFunc("/media/video", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, videoPath)
	})
	mux.HandleFunc("/media/audio", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, filepath.Join(*root, "media", "..", "..", "Anima3", "anima3_16k.wav"))
	})
	mux.HandleFunc("/media/peaks", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, filepath.Join(*root, "state", "peaks.bin"))
	})
	mux.HandleFunc("/media/spectrum", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, filepath.Join(*root, "state", "spectrum.bin"))
	})
	mux.HandleFunc("/media/spectrum/meta", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, filepath.Join(*root, "state", "spectrum.meta.json"))
	})

	// ---- 状态 API ----
	mux.HandleFunc("/api/meta", func(w http.ResponseWriter, r *http.Request) {
		st.mu.Lock()
		g, y, rd := 0, 0, 0
		for _, b := range st.blocks {
			switch b.Confidence {
			case "green":
				g++
			case "yellow":
				y++
			default:
				rd++
			}
		}
		st.mu.Unlock()
		writeJSON(w, map[string]any{"total": len(st.blocks), "green": g, "yellow": y, "red": rd,
			"tags_open": countTags(st, "open")})
	})

	mux.HandleFunc("/api/blocks", func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			// ---- 新建块 ----
			var nb Block
			if err := json.NewDecoder(r.Body).Decode(&nb); err != nil {
				http.Error(w, "bad json: "+err.Error(), 400)
				return
			}
			if nb.Ja == "" || nb.End <= nb.Start {
				http.Error(w, "need ja and valid start/end", 400)
				return
			}
			st.mu.Lock()
			defer st.mu.Unlock()
			// 分配 id: {song}-NNN 或 U-NNN
			prefix := "U"
			if nb.Song != "" {
				prefix = nb.Song
			}
			maxN := 0
			for id := range st.blocks {
				if strings.HasPrefix(id, prefix+"-") {
					var n int
					fmt.Sscanf(strings.SplitN(id, "-", 2)[1], "%d", &n)
					if n > maxN {
						maxN = n
					}
				}
			}
			nb.ID = fmt.Sprintf("%s-%03d", prefix, maxN+1)
			nb.Evidence = map[string]string{"method": "manual_add", "detail": "人工添加"}
			nb.Tags = []string{}
			nb.History = []map[string]any{{"actor": "ui", "ts": time.Now().Format(time.RFC3339),
				"action": "create", "after": map[string]any{"start": nb.Start, "end": nb.End, "ja": nb.Ja, "zh": nb.Zh}}}
			st.blocks[nb.ID] = &nb
			st.order = append(st.order, nb.ID)
			sort.Slice(st.order, func(i, j int) bool {
				return st.blocks[st.order[i]].Start < st.blocks[st.order[j]].Start
			})
			st.dirty = true
			st.save()
			go func() { time.Sleep(5 * time.Second); st.mu.Lock(); st.commit(); st.mu.Unlock() }()
			writeJSON(w, nb)
			return
		}
		st.mu.Lock()
		defer st.mu.Unlock()
		list := make([]*Block, 0, len(st.order))
		for _, id := range st.order {
			list = append(list, st.blocks[id])
		}
		writeJSON(w, map[string]any{"blocks": list})
	})

	mux.HandleFunc("/api/blocks/", func(w http.ResponseWriter, r *http.Request) {
		raw := strings.TrimPrefix(r.URL.Path, "/api/blocks/")
		// ---- 回滚：/api/blocks/{id}/revert/{index} ----
		if strings.Contains(raw, "/revert/") {
			parts := strings.SplitN(raw, "/revert/", 2)
			if len(parts) != 2 || r.Method != http.MethodPost {
				http.Error(w, "bad revert path", 400)
				return
			}
			id, idxStr := parts[0], parts[1]
			idx, err := strconv.Atoi(idxStr)
			if err != nil {
				http.Error(w, "bad index", 400)
				return
			}
			st.mu.Lock()
			defer st.mu.Unlock()
			b, ok := st.blocks[id]
			if !ok {
				http.NotFound(w, r)
				return
			}
			if idx < 0 || idx >= len(b.History) {
				http.Error(w, "history index out of range", 400)
				return
			}
			entry := b.History[idx]
			before, _ := entry["before"].(map[string]any)
			if before != nil {
				if v, ok := before["start"].(float64); ok {
					b.Start = v
				}
				if v, ok := before["end"].(float64); ok {
					b.End = v
				}
				if v, ok := before["ja"].(string); ok {
					b.Ja = v
				}
				if v, ok := before["zh"].(string); ok {
					b.Zh = v
				}
				if v, ok := before["confidence"].(string); ok {
					b.Confidence = v
				}
			}
			b.History = append(b.History, map[string]any{"actor": "revert", "ts": time.Now().Format(time.RFC3339),
				"revert_of": idx, "before": before,
				"after": map[string]any{"start": b.Start, "end": b.End, "ja": b.Ja, "zh": b.Zh, "confidence": b.Confidence}})
			st.dirty = true
			if err := st.save(); err != nil {
				http.Error(w, err.Error(), 500)
				return
			}
			go func() { time.Sleep(5 * time.Second); st.mu.Lock(); st.commit(); st.mu.Unlock() }()
			writeJSON(w, b)
			return
		}
		// ---- 拆块：/api/blocks/{id}/split {"parts":["...","..."]} ----
		if strings.Contains(raw, "/split") {
			id := strings.TrimSuffix(raw, "/split")
			if r.Method != http.MethodPost {
				http.Error(w, "POST only", 405)
				return
			}
			var req struct {
				Parts []string `json:"parts"`
			}
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil || len(req.Parts) < 2 {
				http.Error(w, "bad json: need parts>=2", 400)
				return
			}
			st.mu.Lock()
			defer st.mu.Unlock()
			b, ok := st.blocks[id]
			if !ok {
				http.NotFound(w, r)
				return
			}
			// 按 ja 字符数比例分配时间区间
			total := 0
			for _, p := range req.Parts {
				total += len([]rune(p))
			}
			if total == 0 {
				http.Error(w, "empty parts", 400)
				return
			}
			// 生成子 id：原 id + b/c/d...
			suffix := []string{"b", "c", "d", "e", "f", "g", "h"}
			before := map[string]any{"start": b.Start, "end": b.End, "ja": b.Ja, "zh": b.Zh}
			b.Ja = req.Parts[0]
			children := []map[string]any{}
			cursor := b.Start
			dur := b.End - b.Start
			firstChildStart := b.End
			for i := 1; i < len(req.Parts); i++ {
				frac := float64(len([]rune(req.Parts[i]))) / float64(total)
				childStart := cursor + dur*float64(len([]rune(req.Parts[i-1])))/float64(total)
				childEnd := childStart + dur*frac
				if i == 1 {
					firstChildStart = childStart
				}
				cursor = childEnd
				nid := id + suffix[i-1]
				if _, exists := st.blocks[nid]; exists {
					http.Error(w, "child id exists: "+nid, 409)
					return
				}
				child := &Block{ID: nid, Start: childStart, End: childEnd, Kind: b.Kind, Song: b.Song,
					Ja: req.Parts[i], Zh: "", Confidence: b.Confidence,
					Evidence: b.Evidence, Tags: []string{}, History: []map[string]any{{
						"actor": "split", "ts": time.Now().Format(time.RFC3339),
						"split_from": id, "before": before,
						"after": map[string]any{"start": childStart, "end": childEnd, "ja": req.Parts[i]}}},
					Locked: false}
				st.blocks[nid] = child
				// 插到 order 中原块之后
				pos := -1
				for j, oid := range st.order {
					if oid == id {
						pos = j
						break
					}
				}
				st.order = append(st.order[:pos+1], append([]string{nid}, st.order[pos+1:]...)...)
				children = append(children, map[string]any{"id": nid, "start": childStart, "end": childEnd})
			}
			b.End = firstChildStart
			b.Zh = ""
			b.History = append(b.History, map[string]any{"actor": "split", "ts": time.Now().Format(time.RFC3339),
				"before": before, "children": children,
				"after": map[string]any{"start": b.Start, "end": b.End, "ja": b.Ja}})
			st.dirty = true
			st.save()
			go func() { time.Sleep(5 * time.Second); st.mu.Lock(); st.commit(); st.mu.Unlock() }()
			writeJSON(w, map[string]any{"block": b, "children": children})
			return
		}

		// ---- 合块：/api/blocks/merge {"ids":["a","b"]} ----
		if raw == "merge" {
			if r.Method != http.MethodPost {
				http.Error(w, "POST only", 405)
				return
			}
			var req struct {
				IDs []string `json:"ids"`
			}
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil || len(req.IDs) < 2 {
				http.Error(w, "bad json: need ids>=2", 400)
				return
			}
			st.mu.Lock()
			defer st.mu.Unlock()
			first, ok := st.blocks[req.IDs[0]]
			if !ok {
				http.NotFound(w, r)
				return
			}
			before := map[string]any{"start": first.Start, "end": first.End, "ja": first.Ja, "zh": first.Zh}
			for _, oid := range req.IDs[1:] {
				ob, ok := st.blocks[oid]
				if !ok {
					continue
				}
				first.Ja = first.Ja + "\n" + ob.Ja
				if ob.Zh != "" {
					first.Zh = first.Zh + "\n" + ob.Zh
				}
				first.End = ob.End
				// 迁移 tags 引用
				for _, tid := range ob.Tags {
					first.Tags = append(first.Tags, tid)
					if t, ok := st.tags[tid]; ok {
						t.BlockID = first.ID
					}
				}
				delete(st.blocks, oid)
				newOrder := st.order[:0]
				for _, x := range st.order {
					if x != oid {
						newOrder = append(newOrder, x)
					}
				}
				st.order = newOrder
			}
			first.History = append(first.History, map[string]any{"actor": "merge", "ts": time.Now().Format(time.RFC3339),
				"merged_ids": req.IDs[1:], "before": before,
				"after": map[string]any{"start": first.Start, "end": first.End, "ja": first.Ja, "zh": first.Zh}})
			st.dirty = true
			st.save()
			go func() { time.Sleep(5 * time.Second); st.mu.Lock(); st.commit(); st.mu.Unlock() }()
			writeJSON(w, first)
			return
		}

		id := raw
		st.mu.Lock()
		defer st.mu.Unlock()
		b, ok := st.blocks[id]
		if !ok {
			http.NotFound(w, r)
			return
		}
		switch r.Method {
		case http.MethodDelete:
			// ---- 删除块 ----
			before := map[string]any{"start": b.Start, "end": b.End, "ja": b.Ja, "zh": b.Zh, "confidence": b.Confidence}
			delete(st.blocks, id)
			newOrder := st.order[:0]
			for _, x := range st.order {
				if x != id {
					newOrder = append(newOrder, x)
				}
			}
			st.order = newOrder
			st.dirty = true
			st.save()
			go func() { time.Sleep(5 * time.Second); st.mu.Lock(); st.commit(); st.mu.Unlock() }()
			writeJSON(w, map[string]any{"deleted": id, "before": before})
			return
		case http.MethodPut:
			var ch map[string]any
			if err := json.NewDecoder(r.Body).Decode(&ch); err != nil {
				http.Error(w, "bad json", 400)
				return
			}
			before := map[string]any{"start": b.Start, "end": b.End, "ja": b.Ja, "zh": b.Zh, "confidence": b.Confidence}
			if v, ok := ch["start"].(float64); ok {
				b.Start = v
			}
			if v, ok := ch["end"].(float64); ok {
				b.End = v
			}
			if v, ok := ch["ja"].(string); ok {
				b.Ja = v
			}
			if v, ok := ch["zh"].(string); ok {
				b.Zh = v
			}
			if v, ok := ch["confidence"].(string); ok {
				b.Confidence = v
			}
			if v, ok := ch["locked"].(bool); ok {
				b.Locked = v
			}
			entry := map[string]any{"actor": "ui", "ts": time.Now().Format(time.RFC3339), "before": before,
				"after": map[string]any{"start": b.Start, "end": b.End, "ja": b.Ja, "zh": b.Zh, "confidence": b.Confidence}}
			b.History = append(b.History, entry)
			st.dirty = true
			if err := st.save(); err != nil {
				http.Error(w, err.Error(), 500)
				return
			}
			go func() { time.Sleep(5 * time.Second); st.mu.Lock(); st.commit(); st.mu.Unlock() }()
			writeJSON(w, b)
		default:
			writeJSON(w, b)
		}
	})

	// ---- 整段平移：从 from 起的所有块平移 delta 秒 ----
	mux.HandleFunc("/api/shift", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", 405)
			return
		}
		var req struct {
			From  float64 `json:"from"`
			Delta float64 `json:"delta"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "bad json: "+err.Error(), 400)
			return
		}
		if req.Delta == 0 {
			writeJSON(w, map[string]any{"shifted": 0})
			return
		}
		st.mu.Lock()
		defer st.mu.Unlock()
		n := 0
		for _, id := range st.order {
			b := st.blocks[id]
			if b.Start < req.From {
				continue
			}
			before := map[string]any{"start": b.Start, "end": b.End}
			b.Start += req.Delta
			b.End += req.Delta
			if b.Start < 0 {
				b.Start = 0
			}
			if b.End < b.Start {
				b.End = b.Start + 0.1
			}
			b.History = append(b.History, map[string]any{"actor": "ui", "ts": time.Now().Format(time.RFC3339),
				"shift": req.Delta, "before": before,
				"after": map[string]any{"start": b.Start, "end": b.End}})
			n++
		}
		st.dirty = true
		st.save()
		go func() { time.Sleep(5 * time.Second); st.mu.Lock(); st.commit(); st.mu.Unlock() }()
		writeJSON(w, map[string]any{"shifted": n})
	})

	// ---- tags ----
	mux.HandleFunc("/api/tags", func(w http.ResponseWriter, r *http.Request) {
		st.mu.Lock()
		defer st.mu.Unlock()
		switch r.Method {
		case http.MethodGet:
			list := make([]*Tag, 0, len(st.tags))
			for _, t := range st.tags {
				list = append(list, t)
			}
			sort.Slice(list, func(i, j int) bool { return list[i].Created < list[j].Created })
			writeJSON(w, map[string]any{"tags": list})
		case http.MethodPost:
			var t Tag
			if err := json.NewDecoder(r.Body).Decode(&t); err != nil {
				http.Error(w, "bad json", 400)
				return
			}
			t.ID = fmt.Sprintf("T%06d", time.Now().UnixNano()%1_000_000)
			t.Status = "open"
			t.Created = time.Now().Format(time.RFC3339)
			st.tags[t.ID] = &t
			if t.BlockID != "" {
				if b, ok := st.blocks[t.BlockID]; ok {
					b.Tags = append(b.Tags, t.ID)
				}
			}
			st.dirty = true
			st.save()
			writeJSON(w, t)
		}
	})

	// ---- 曲目列表 ----
	mux.HandleFunc("/api/songs", func(w http.ResponseWriter, r *http.Request) {
		data, err := os.ReadFile(filepath.Join(*root, "state", "songs.json"))
		if err != nil {
			writeJSON(w, map[string]any{"songs": []any{}})
			return
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Write(data)
	})

	// ---- 官方歌词（网易云）----
	mux.HandleFunc("/api/lyrics", func(w http.ResponseWriter, r *http.Request) {
		data, err := os.ReadFile(filepath.Join(*root, "state", "lyrics.json"))
		if err != nil {
			writeJSON(w, map[string]any{"songs": []any{}})
			return
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Write(data)
	})

	// ---- 歌词(live 时间轴对齐版) ----
	mux.HandleFunc("/api/lyrics_live", func(w http.ResponseWriter, r *http.Request) {
		data, err := os.ReadFile(filepath.Join(*root, "state", "lyrics_live.json"))
		if err != nil {
			writeJSON(w, map[string]any{"songs": []any{}})
			return
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Write(data)
	})

	// ---- 演出环节结构 ----
	mux.HandleFunc("/api/segments", func(w http.ResponseWriter, r *http.Request) {
		data, err := os.ReadFile(filepath.Join(*root, "state", "segments.json"))
		if err != nil {
			writeJSON(w, map[string]any{"segments": []any{}})
			return
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Write(data)
	})

	// ---- DTW 映射曲线 ----
	mux.HandleFunc("/api/dtw/", func(w http.ResponseWriter, r *http.Request) {
		sid := strings.TrimPrefix(r.URL.Path, "/api/dtw/")
		// 优先 anchored 映射, 回退全局映射
		for _, name := range []string{sid + ".anchored.json", sid + ".map.json"} {
			data, err := os.ReadFile(filepath.Join(*root, "state", "dtw", name))
			if err == nil {
				w.Header().Set("Content-Type", "application/json; charset=utf-8")
				w.Write(data)
				return
			}
		}
		writeJSON(w, map[string]any{"live_t": []float64{}, "studio_t": []float64{}})
	})

	// ---- 标记生命周期：人工改状态（done/rejected/open）----
	mux.HandleFunc("/api/tags/status", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", 405)
			return
		}
		var req struct {
			ID     string `json:"id"`
			Status string `json:"status"`
			Reply  string `json:"reply,omitempty"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "bad json: "+err.Error(), 400)
			return
		}
		if req.Status != "open" && req.Status != "done" && req.Status != "rejected" && req.Status != "processing" {
			http.Error(w, "bad status", 400)
			return
		}
		st.mu.Lock()
		defer st.mu.Unlock()
		t, ok := st.tags[req.ID]
		if !ok {
			http.NotFound(w, r)
			return
		}
		t.Status = req.Status
		if req.Reply != "" {
			t.Reply = req.Reply
		}
		st.dirty = true
		st.save()
		writeJSON(w, t)
	})

	// ---- 删除标记 ----
	mux.HandleFunc("/api/tags/", func(w http.ResponseWriter, r *http.Request) {
		// 编辑: PUT /api/tags/{id} {type, note}
		if r.Method == http.MethodPut {
			id := strings.TrimPrefix(r.URL.Path, "/api/tags/")
			var req struct {
				Type string `json:"type"`
				Note string `json:"note"`
			}
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				http.Error(w, "bad json: "+err.Error(), 400)
				return
			}
			st.mu.Lock()
			defer st.mu.Unlock()
			t, ok := st.tags[id]
			if !ok {
				http.NotFound(w, r)
				return
			}
			if req.Type != "" {
				t.Type = req.Type
			}
			t.Note = req.Note
			st.dirty = true
			st.save()
			writeJSON(w, t)
			return
		}
		if r.Method != http.MethodDelete {
			http.Error(w, "PUT/DELETE only", 405)
			return
		}
		id := strings.TrimPrefix(r.URL.Path, "/api/tags/")
		st.mu.Lock()
		defer st.mu.Unlock()
		t, ok := st.tags[id]
		if !ok {
			http.NotFound(w, r)
			return
		}
		// 从块的 tags 引用中移除
		if t.BlockID != "" {
			if b, ok := st.blocks[t.BlockID]; ok {
				out := b.Tags[:0]
				for _, tid := range b.Tags {
					if tid != id {
						out = append(out, tid)
					}
				}
				b.Tags = out
			}
		}
		delete(st.tags, id)
		st.dirty = true
		st.save()
		writeJSON(w, map[string]any{"deleted": id})
	})

	// ---- patches（agent 回写）----
	mux.HandleFunc("/api/patches", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", 405)
			return
		}
		var patches []Patch
		if err := json.NewDecoder(r.Body).Decode(&patches); err != nil {
			http.Error(w, "bad json: "+err.Error(), 400)
			return
		}
		st.mu.Lock()
		defer st.mu.Unlock()
		applied := 0
		for _, p := range patches {
			b, ok := st.blocks[p.BlockID]
			if !ok {
				continue
			}
			before := map[string]any{"start": b.Start, "end": b.End, "ja": b.Ja, "zh": b.Zh, "confidence": b.Confidence}
			if v, ok := p.Changes["start"].(float64); ok {
				b.Start = v
			}
			if v, ok := p.Changes["end"].(float64); ok {
				b.End = v
			}
			if v, ok := p.Changes["ja"].(string); ok {
				b.Ja = v
			}
			if v, ok := p.Changes["zh"].(string); ok {
				b.Zh = v
			}
			if v, ok := p.Changes["confidence"].(string); ok {
				b.Confidence = v
			}
			entry := map[string]any{"actor": "agent", "ts": time.Now().Format(time.RFC3339), "patch_id": p.ID,
				"reply": p.Reply, "before": before,
				"after": map[string]any{"start": b.Start, "end": b.End, "ja": b.Ja, "zh": b.Zh, "confidence": b.Confidence}}
			b.History = append(b.History, entry)
			if p.TagID != "" {
				if t, ok := st.tags[p.TagID]; ok {
					t.Status = "done"
					t.Reply = p.Reply
				}
			}
			applied++
		}
		st.dirty = true
		st.save()
		go func() { time.Sleep(5 * time.Second); st.mu.Lock(); st.commit(); st.mu.Unlock() }()
		writeJSON(w, map[string]any{"applied": applied})
	})

	// ---- git ----
	mux.HandleFunc("/api/git/log", func(w http.ResponseWriter, r *http.Request) {
		out, _ := exec.Command("git", "-C", *root, "log", "--oneline", "-20").CombinedOutput()
		writeJSON(w, map[string]any{"log": string(out)})
	})
	mux.HandleFunc("/api/git/diff", func(w http.ResponseWriter, r *http.Request) {
		from := r.URL.Query().Get("from")
		to := r.URL.Query().Get("to")
		if from == "" {
			from = "HEAD"
		}
		args := []string{"-C", *root, "diff", from}
		if to != "" {
			args = append(args, to)
		}
		out, _ := exec.Command("git", args...).CombinedOutput()
		writeJSON(w, map[string]any{"diff": string(out)})
	})

	// ---- 导出 ----
	mux.HandleFunc("/api/export", func(w http.ResponseWriter, r *http.Request) {
		fmt_ := r.URL.Query().Get("fmt")
		if fmt_ != "srt" && fmt_ != "ass" {
			fmt_ = "srt"
		}
		onlyGreen := r.URL.Query().Get("only") == "green"
		st.mu.Lock()
		defer st.mu.Unlock()
		fname := "anima3_edited"
		if onlyGreen {
			fname += "_green"
		}
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s.%s"`, fname, fmt_))
		if fmt_ == "srt" {
			writeSrt(w, st, onlyGreen)
		} else {
			writeAss(w, st, onlyGreen)
		}
	})

	addr := "127.0.0.1:8720"
	log.Printf("[agentisub] serving at http://%s (root=%s)", addr, *root)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatal(err)
	}
}

func countTags(st *Store, status string) int {
	n := 0
	for _, t := range st.tags {
		if t.Status == status {
			n++
		}
	}
	return n
}

func fmtSrt(sec float64) string {
	ms := int(sec*1000 + 0.5)
	return fmt.Sprintf("%02d:%02d:%02d,%03d", ms/3600000, ms/60000%60, ms/1000%60, ms%1000)
}

func writeSrt(w http.ResponseWriter, st *Store, onlyGreen bool) {
	// UTF-8 BOM（Windows 播放器/老版 PotPlayer 兼容）
	w.Write([]byte{0xEF, 0xBB, 0xBF})
	i := 0
	for _, id := range st.order {
		b := st.blocks[id]
		if onlyGreen && b.Confidence != "green" {
			continue
		}
		i++
		fmt.Fprintf(w, "%d\n%s --> %s\n%s\n", i, fmtSrt(b.Start), fmtSrt(b.End), b.Ja)
		if b.Zh != "" {
			fmt.Fprintf(w, "%s\n", b.Zh)
		}
		fmt.Fprintln(w)
	}
}

func assTs(sec float64) string {
	t := sec
	h := int(t) / 3600
	m := int(t) % 3600 / 60
	return fmt.Sprintf("%d:%02d:%05.2f", h, m, t-float64(h*3600+m*60))
}

func writeAss(w http.ResponseWriter, st *Store, onlyGreen bool) {
	fmt.Fprint(w, `[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyric,Yu Gothic UI,54,&H00FFFFFF,&H000000FF,&H00141414,&H78000000,0,0,0,0,100,100,0,0,1,2.5,0,5,60,60,30,1
Style: Talk,Yu Gothic UI,48,&H00FFFFFF,&H000000FF,&H00141414,&H78000000,0,0,0,0,100,100,0,0,1,2,0,2,80,80,45,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
`)
	for _, id := range st.order {
		b := st.blocks[id]
		if onlyGreen && b.Confidence != "green" {
			continue
		}
		style := "Talk"
		if b.Kind == "lyric" {
			style = "Lyric"
		}
		text := b.Ja
		if b.Zh != "" {
			text = fmt.Sprintf(`{\fs52}%s\N{\fs36}%s`, strings.ReplaceAll(b.Ja, `\`, ""), strings.ReplaceAll(b.Zh, "\n", " "))
		}
		text = strings.ReplaceAll(text, "{", "（")
		text = strings.ReplaceAll(text, "}", "）")
		fmt.Fprintf(w, "Dialogue: 0,%s,%s,%s,,0,0,0,,%s\n", assTs(b.Start), assTs(b.End), style, text)
	}
}
