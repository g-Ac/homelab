# sem-pensar: proxy Bifrost → Ollama que impõe reasoning_effort "none" por padrão (issue #13).
# Só biblioteca padrão do Go. Binário estático em imagem vazia, sem shell, rodando sem root.
# golang:1.27.3-alpine, fixado por digest (ADR 0004). O 1.27.3 traz as correções de net/http
# e crypto/tls de 20/10/2026 (#14), que importam para um proxy HTTP.
FROM golang@sha256:b8c9b82affbbb82a020bbcf998dad2ba9516944ac7e883524642a481a9505e9c AS build
WORKDIR /src
COPY go.mod main.go main_test.go ./
RUN go vet ./... && go test ./... && CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /sem-pensar .

FROM scratch
COPY --from=build /sem-pensar /sem-pensar
USER 65534:65534
EXPOSE 11434
ENTRYPOINT ["/sem-pensar"]
