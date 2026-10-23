package main

import (
	"bufio"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

func decodificar(t *testing.T, b []byte) map[string]any {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatalf("JSON inválido: %v: %s", err, b)
	}
	return m
}

func TestAjustarInjetaQuandoAusente(t *testing.T) {
	novo := ajustar([]byte(`{"model":"qwen3.5:4b","messages":[{"role":"user","content":"oi"}],"temperature":0}`))
	if novo == nil {
		t.Fatal("deveria injetar")
	}
	m := decodificar(t, novo)
	if m["reasoning_effort"] != "none" {
		t.Errorf("reasoning_effort = %v, quero none", m["reasoning_effort"])
	}
	if m["model"] != "qwen3.5:4b" || m["temperature"] != 0.0 {
		t.Errorf("campos originais alterados: %v", m)
	}
	if len(m["messages"].([]any)) != 1 {
		t.Errorf("messages alterado: %v", m["messages"])
	}
}

func TestAjustarPreservaEscolhaDoCliente(t *testing.T) {
	casos := []string{
		`{"model":"qwen3.5:4b","reasoning_effort":"high"}`,
		`{"model":"qwen3.5:4b","reasoning_effort":null}`,
		`{"model":"qwen3.5:4b","reasoning":{"effort":"low"}}`,
	}
	for _, c := range casos {
		if novo := ajustar([]byte(c)); novo != nil {
			t.Errorf("não deveria mexer em %s, virou %s", c, novo)
		}
	}
}

func TestAjustarIgnoraOQueNaoEObjeto(t *testing.T) {
	for _, c := range []string{`{nope`, `[1,2]`, `null`, `"texto"`, ``} {
		if novo := ajustar([]byte(c)); novo != nil {
			t.Errorf("não deveria mexer em %q, virou %s", c, novo)
		}
	}
}

type recebido struct {
	caminho string
	corpo   []byte
	host    string
}

func subirPar(t *testing.T, resposta http.HandlerFunc) (*httptest.Server, *httptest.Server, *recebido) {
	t.Helper()
	rec := &recebido{}
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rec.caminho = r.URL.Path
		rec.host = r.Host
		rec.corpo, _ = io.ReadAll(r.Body)
		if resposta != nil {
			resposta(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	u, _ := url.Parse(upstream.URL)
	proxy := httptest.NewServer(novoProxy(u))
	t.Cleanup(func() { proxy.Close(); upstream.Close() })
	return proxy, upstream, rec
}

func TestProxyInjetaSoNoChatCompletions(t *testing.T) {
	proxy, upstream, rec := subirPar(t, nil)

	r, err := http.Post(proxy.URL+"/v1/chat/completions", "application/json",
		strings.NewReader(`{"model":"qwen3.5:4b","messages":[]}`))
	if err != nil || r.StatusCode != 200 {
		t.Fatalf("chat: %v %v", err, r)
	}
	if m := decodificar(t, rec.corpo); m["reasoning_effort"] != "none" {
		t.Errorf("upstream recebeu %s, sem injeção", rec.corpo)
	}
	if u, _ := url.Parse(upstream.URL); rec.host != u.Host {
		t.Errorf("Host = %q, quero %q", rec.host, u.Host)
	}

	original := `{"model":"qwen3.5:4b","messages":[],"think":false}`
	r, _ = http.Post(proxy.URL+"/api/chat", "application/json", strings.NewReader(original))
	if r.StatusCode != 200 || string(rec.corpo) != original || rec.caminho != "/api/chat" {
		t.Errorf("/api/chat deveria passar intacto: %s em %s", rec.corpo, rec.caminho)
	}

	r, _ = http.Get(proxy.URL + "/api/tags")
	if r.StatusCode != 200 || rec.caminho != "/api/tags" {
		t.Errorf("GET /api/tags deveria passar: HTTP %d em %s", r.StatusCode, rec.caminho)
	}
}

func TestProxyPreservaValorDoCliente(t *testing.T) {
	proxy, _, rec := subirPar(t, nil)
	original := `{"model":"qwen3.5:4b","messages":[],"reasoning_effort":"high"}`
	_, _ = http.Post(proxy.URL+"/v1/chat/completions", "application/json", strings.NewReader(original))
	if string(rec.corpo) != original {
		t.Errorf("corpo com valor do cliente deveria passar byte a byte: %s", rec.corpo)
	}
}

func TestProxyRepassaStreamingSemSegurar(t *testing.T) {
	liberar := make(chan struct{})
	proxy, _, _ := subirPar(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		fl := w.(http.Flusher)
		_, _ = io.WriteString(w, "data: um\n\n")
		fl.Flush()
		<-liberar // só manda o segundo pedaço depois que o cliente leu o primeiro
		_, _ = io.WriteString(w, "data: [DONE]\n\n")
	})
	r, err := http.Post(proxy.URL+"/v1/chat/completions", "application/json",
		strings.NewReader(`{"model":"qwen3.5:4b","messages":[],"stream":true}`))
	if err != nil {
		t.Fatal(err)
	}
	defer r.Body.Close()
	leitor := bufio.NewReader(r.Body)
	linha, err := leitor.ReadString('\n')
	if err != nil || linha != "data: um\n" {
		t.Fatalf("primeiro pedaço não chegou antes do fim: %q %v", linha, err)
	}
	close(liberar)
	resto, _ := io.ReadAll(leitor)
	if !strings.Contains(string(resto), "[DONE]") {
		t.Errorf("fim do stream não chegou: %q", resto)
	}
	if ct := r.Header.Get("Content-Type"); ct != "text/event-stream" {
		t.Errorf("Content-Type = %q", ct)
	}
}

func TestProxyRecusaCorpoGrande(t *testing.T) {
	proxy, _, _ := subirPar(t, nil)
	grande := strings.NewReader(`{"model":"x","messages":["` + strings.Repeat("a", limiteCorpo) + `"]}`)
	r, err := http.Post(proxy.URL+"/v1/chat/completions", "application/json", grande)
	if err != nil || r.StatusCode != http.StatusRequestEntityTooLarge {
		t.Fatalf("quero 413, veio %v %v", r, err)
	}
}
