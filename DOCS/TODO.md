# TODO

- [ ] 국가별 신규 기사 수신 이벤트(SSE/WebSocket 등) API가 마련되면 위성의 ‘수신 시뮬레이션’을 실제 이벤트로 교체한다. 현재는 보이는 국가 좌표에서 2.4초 간격으로 전송을 연출하며, 실제 기사 수신을 뜻하지 않는다. 타임머신과 모션 감소 설정에서는 전송 애니메이션을 중지한다.

- [x] 국가별 보도 관점 API를 프론트에 연결한다. `GET /api/v1/global/issues/{issueId}/country-analyses`의 `countryAnalyses`를 국가별 논조와 합쳐 목록·지구본 요약에 표시한다. 국가 선택 시 `GET /api/v1/global/issues/{issueId}/country-analyses/{countryCode}`의 `analysis`를 조회해 기존 대시보드 상세 영역과 지구본 카드에 표시한다. 상세 필드는 `title`, `summary`, `details`(문자열 배열), `articleCount`, `windowEnd`이며, 분석이 없으면 `analysis: null`이다. 두 요청 모두 타임머신의 `asOf`와 요청 취소를 지원하며, 분석 요청 실패는 논조·대표 기사 표시를 막지 않는다. 대표 기사는 분석 근거 기사와 별개다.

- [ ] 타임머신의 실제 화면 복원 정밀도가 필요해지면 이슈 배정 이벤트 시각과 DB 반영 시각을 구분하고 중복 이벤트의 최초 배정 시각 보존을 검토한다.
- [ ] 타임머신 조회를 운영 규모 데이터에서 측정한다. 삭제 시점 조건 추가에 따른 기존 부분 인덱스 사용 여부를 확인한 뒤 필요한 변경만 결정한다.
