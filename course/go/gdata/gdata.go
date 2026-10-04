// Package gdata gets the game data G: the tables of items, monsters, skills,
// maps and more that the game client reads. It downloads G one time per
// version and keeps a copy on disk, because G is a few MB.
// Standard library only.
package gdata

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// region types

// ItemDef is G.items[name]. Only the fields that the course reads;
// encoding/json ignores the other fields.
type ItemDef struct {
	Name     string   `json:"name"`     // the display name, "HP Potion"
	Type     string   `json:"type"`     // "weapon", "pot", "material", ...
	G        int      `json:"g"`        // the value in gold (also the NPC price)
	S        int      `json:"s"`        // the maximum stack; 0 = the item does not stack
	Gives    [][2]any `json:"gives"`    // potions: [stat, amount] pairs, ["hp", 200]
	Cooldown float64  `json:"cooldown"` // potions: ms until the next potion
}

// MonsterDef is G.monsters[type]. A monster in an `entities` event has only
// the fields that are different from this definition.
type MonsterDef struct {
	Name       string  `json:"name"`
	HP         float64 `json:"hp"` // also the max_hp of a new monster
	Attack     float64 `json:"attack"`
	Speed      float64 `json:"speed"`     // px per second
	Range      float64 `json:"range"`     // px
	Frequency  float64 `json:"frequency"` // attacks per second
	XP         float64 `json:"xp"`
	Respawn    float64 `json:"respawn"`     // SECONDS (most durations are ms); -1 = never by itself
	Size       float64 `json:"size"`        // scales G.dimensions; 0 = not set
	DamageType string  `json:"damage_type"` // "physical", "magical", ...
}

// SkillDef is G.skills[name].
type SkillDef struct {
	Name     string   `json:"name"`
	Type     string   `json:"type"`
	Cooldown float64  `json:"cooldown"` // ms
	MP       float64  `json:"mp"`       // the mana cost
	Range    float64  `json:"range"`
	Share    string   `json:"share"` // this skill uses the cooldown of another skill
	Class    []string `json:"class"`
	Level    int      `json:"level"`
}

// GData is G: the tables that we typed, plus every table as raw JSON in
// Tables (maps, geometry, npcs, classes, ...). Decode a raw table when you
// need it: json.Unmarshal(G.Tables["classes"], &classes).
type GData struct {
	Version  int                   `json:"version"`
	Items    map[string]ItemDef    `json:"items"`
	Monsters map[string]MonsterDef `json:"monsters"`
	Skills   map[string]SkillDef   `json:"skills"`
	// G.dimensions[type] = [width, height, ...] of a sprite; world.Distance uses it.
	Dimensions map[string][]float64 `json:"dimensions"`

	Tables map[string]json.RawMessage `json:"-"` // every table of G, not decoded
}

// Parse decodes the JSON text of G.
func Parse(raw []byte) (*GData, error) {
	g := &GData{}
	if err := json.Unmarshal(raw, g); err != nil {
		return nil, fmt.Errorf("parse G: %w", err)
	}
	if err := json.Unmarshal(raw, &g.Tables); err != nil {
		return nil, fmt.Errorf("parse G: %w", err)
	}
	return g, nil
}

// endregion types

// get returns the body of GET url as text.
func get(ctx context.Context, url string) (string, error) {
	// 60 s: G is a few MB, and a slow link needs time for it.
	ctx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return "", err
	}
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", err
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return "", fmt.Errorf("GET %s: HTTP %d", url, res.StatusCode)
	}
	b, err := io.ReadAll(res.Body)
	return string(b), err
}

// region fetch-version

// The game page has the line var VERSION='17478' (htmls/base_script.html:32).
var versionRe = regexp.MustCompile(`var\s+VERSION\s*=\s*'(\d+)'`)

// FetchVersion reads the version of G from the game page /hub. It returns 0
// when the page has no version.
func FetchVersion(ctx context.Context, base string) (int, error) {
	html, err := get(ctx, base+"/hub")
	if err != nil {
		return 0, err
	}
	m := versionRe.FindStringSubmatch(html)
	if m == nil {
		return 0, nil
	}
	return strconv.Atoi(m[1])
}

// endregion fetch-version

// region download-g

// downloadRaw returns the JSON text of G. /data.js is JavaScript,
// "var G={...};" (web_assets.js:52): the JSON is the text from the first "{"
// to the last "}".
func downloadRaw(ctx context.Context, base string) ([]byte, error) {
	js, err := get(ctx, base+"/data.js")
	if err != nil {
		return nil, err
	}
	start, end := strings.Index(js, "{"), strings.LastIndex(js, "}")
	if start < 0 || end < start {
		return nil, errors.New("data.js: no JSON object found")
	}
	return []byte(js[start : end+1]), nil
}

// DownloadG downloads G and decodes it. It does not use the cache.
func DownloadG(ctx context.Context, base string) (*GData, error) {
	raw, err := downloadRaw(ctx, base)
	if err != nil {
		return nil, err
	}
	return Parse(raw)
}

// endregion download-g

// CachePath is the file for one version of G from one site:
// .al-cache/<host>/G_<version>.json. <host> is the host and port of base,
// with ":" changed to "_" (a file name on Windows cannot have ":"). Thus the
// small G of the test server never mixes with the live G.
func CachePath(base string, version int) string {
	host := base
	if u, err := url.Parse(base); err == nil && u.Host != "" {
		host = u.Host
	}
	host = strings.ReplaceAll(host, ":", "_")
	return filepath.Join(".al-cache", host, fmt.Sprintf("G_%d.json", version))
}

// region load-g

// LoadG returns G from the cache if the cache has the current version. Else
// it downloads G, saves it in the cache and prints "downloaded G version <n>".
func LoadG(ctx context.Context, base string) (*GData, error) {
	version, err := FetchVersion(ctx, base)
	if err != nil {
		return nil, err
	}
	if version != 0 {
		if raw, err := os.ReadFile(CachePath(base, version)); err == nil {
			return Parse(raw) // a cache hit: no download
		}
	}
	raw, err := downloadRaw(ctx, base)
	if err != nil {
		return nil, err
	}
	g, err := Parse(raw)
	if err != nil {
		return nil, err
	}
	// Save under the version that G itself has. If /hub had no version, the
	// next run downloads again, but it is still correct.
	path := CachePath(base, g.Version)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, err
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		return nil, err
	}
	fmt.Println("downloaded G version", g.Version)
	return g, nil
}

// endregion load-g
