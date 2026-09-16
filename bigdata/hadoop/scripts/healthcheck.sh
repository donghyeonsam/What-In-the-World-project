#!/usr/bin/env bash
set -euo pipefail

# Bash의 /dev/tcp와 기본 유틸리티만 사용해 healthcheck마다 Hadoop client
# JVM을 새로 시작하지 않는다. Docker의 healthcheck timeout이 연결 및 응답
# 대기 시간의 상한을 담당한다.
http_get() {
  local host="$1"
  local port="$2"
  local path="$3"
  local response

  exec 3<>"/dev/tcp/${host}/${port}"
  printf 'GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n' \
    "$path" "$host" >&3
  # NUL 문자가 없는 HTTP 텍스트 응답을 EOF까지 Bash 내장 read로 읽는다.
  IFS= read -r -d '' response <&3 || true
  exec 3<&-
  exec 3>&-

  [[ "$response" =~ ^HTTP/1\.[01][[:space:]]+200([[:space:]]|$) ]]
  printf '%s' "$response"
}

case "${1:-}" in
  namenode)
    namenode_response="$(http_get 127.0.0.1 9870 \
      '/jmx?qry=Hadoop:service=NameNode,name=FSNamesystemState')"
    [[ "$namenode_response" =~ \"NumLiveDataNodes\"[[:space:]]*:[[:space:]]*[0-9]+ ]]
    ;;
  datanode)
    datanode_response="$(http_get 127.0.0.1 9864 /jmx)"
    [[ "$datanode_response" =~ \"NumFailedVolumes\"[[:space:]]*:[[:space:]]*0[[:space:]]*([,}]) ]]

    namenode_response="$(http_get namenode 9870 \
      '/jmx?qry=Hadoop:service=NameNode,name=FSNamesystemState')"
    [[ "$namenode_response" =~ \"NumLiveDataNodes\"[[:space:]]*:[[:space:]]*[1-9][0-9]*[[:space:]]*([,}]) ]]
    ;;
  *)
    echo "usage: $0 {namenode|datanode}" >&2
    exit 2
    ;;
esac
