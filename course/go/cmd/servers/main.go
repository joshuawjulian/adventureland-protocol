// cmd/servers/main.go: get the list of game servers over HTTP and print the
// WebSocket URL of each. Standard library only (no albot package).
//
//	Run: go run ./cmd/servers    (AL_BASE_URL: the site; default https://adventure.land)
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
)

// Server is one item of the reply. Only the fields that we use: the
// `json:"..."` tags give the JSON key of each field.
type Server struct {
	Region  string `json:"region"`  // "EU", "US", "ASIA"
	Name    string `json:"name"`    // "I", "II", "PVP", ...
	Address string `json:"address"` // the host (and port), e.g. "eu1.adventure.land"
	Path    string `json:"path"`    // the Socket.IO path, e.g. "/ws1/"
}

// ServerList is the reply of get_servers.
type ServerList struct {
	Success bool     `json:"success"`
	Servers []Server `json:"servers"`
}

func main() {
	base := strings.TrimRight(os.Getenv("AL_BASE_URL"), "/")
	if base == "" {
		base = "https://adventure.land"
	}
	res, err := http.Get(base + "/api/get_servers")
	if err != nil {
		log.Fatal(err) // no connection, DNS failure, ...
	}
	// Always close the body. If you don't, the connection leaks.
	defer res.Body.Close()
	fmt.Println("status:", res.StatusCode, res.Header.Get("Content-Type")) // 200 = OK
	if res.StatusCode != http.StatusOK {
		log.Fatalf("HTTP %d", res.StatusCode)
	}

	var body ServerList
	if err := json.NewDecoder(res.Body).Decode(&body); err != nil {
		log.Fatal(err) // bad JSON, or a value of the wrong type
	}
	// The socket scheme follows the site: http -> ws, https -> wss.
	scheme := "wss"
	if strings.HasPrefix(base, "http://") {
		scheme = "ws"
	}
	for _, s := range body.Servers {
		// The path must end with exactly one "/" (the server matches "/ws1/").
		path := strings.TrimRight(s.Path, "/") + "/"
		url := scheme + "://" + s.Address + path + "?EIO=4&transport=websocket&map_protocol=1&no_graphics=1"
		fmt.Printf("%s %s: %s\n", s.Region, s.Name, url)
	}
}
