// sem-pensar: proxy mínimo entre o Bifrost e o Ollama (issue #13).
//
// Em POST /v1/chat/completions sem `reasoning_effort` nem `reasoning`, injeta
// `reasoning_effort: "none"`: os modelos locais param de "pensar" por padrão.
// O valor que o cliente mandar é preservado. Todo o resto (outros caminhos,
// cabeçalhos, streaming) passa intacto. Não guarda segredo e não registra conteúdo.
package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"time"
)

// Mesmo limite do Bifrost (max_request_body_size_mb).
const limiteCorpo = 10 << 20

// ajustar devolve o corpo com reasoning_effort "none" injetado, ou nil quando
// não há o que mudar (cliente já escolheu, ou o corpo não é um objeto JSON).
func ajustar(corpo []byte) []byte {
	var m map[string]json.RawMessage
	if err := json.Unmarshal(corpo, &m); err != nil || m == nil {
		return nil
	}
	if _, ok := m["reasoning_effort"]; ok {
		return nil
	}
	if _, ok := m["reasoning"]; ok {
		return nil
	}
	m["reasoning_effort"] = json.RawMessage(`"none"`)
	novo, err := json.Marshal(m)
	if err != nil {
		return nil
	}
	return novo
}

// modelo extrai só o nome do modelo, para o log (nunca o conteúdo).
func modelo(corpo []byte) string {
	var m struct {
		Model string `json:"model"`
	}
	_ = json.Unmarshal(corpo, &m)
	return m.Model
}

func novoProxy(upstream *url.URL) http.Handler {
	rp := httputil.NewSingleHostReverseProxy(upstream)
	rp.FlushInterval = -1 // streaming: repassa cada pedaço assim que chega
	diretor := rp.Director
	rp.Director = func(r *http.Request) {
		diretor(r)
		r.Host = upstream.Host
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/v1/chat/completions" && r.Header.Get("Content-Encoding") == "" {
			corpo, err := io.ReadAll(http.MaxBytesReader(w, r.Body, limiteCorpo))
			if err != nil {
				http.Error(w, "corpo ilegível ou acima de 10 MB", http.StatusRequestEntityTooLarge)
				return
			}
			if novo := ajustar(corpo); novo != nil {
				corpo = novo
				log.Printf("injetado reasoning_effort=none (modelo %q)", modelo(corpo))
			}
			r.Body = io.NopCloser(bytes.NewReader(corpo))
			r.ContentLength = int64(len(corpo))
			r.Header.Del("Content-Length")
		}
		rp.ServeHTTP(w, r)
	})
}

func env(nome, padrao string) string {
	if v := os.Getenv(nome); v != "" {
		return v
	}
	return padrao
}

func main() {
	destino := env("SEM_PENSAR_UPSTREAM", "http://ollama:11434")
	porta := env("SEM_PENSAR_PORTA", "11434")
	u, err := url.Parse(destino)
	if err != nil || u.Host == "" {
		log.Fatalf("SEM_PENSAR_UPSTREAM inválido: %q", destino)
	}
	srv := &http.Server{
		Addr:              ":" + porta,
		Handler:           novoProxy(u),
		ReadHeaderTimeout: 10 * time.Second,
	}
	log.Printf("sem-pensar ouvindo em :%s, repassando para %s", porta, destino)
	log.Fatal(srv.ListenAndServe())
}
