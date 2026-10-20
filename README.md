# stock-radar-prices

'이슬의 종목 레이더'용 시세 수집기. `tickers.json`의 종목 시세를 GitHub Actions가 받아 `prices.json`에 기록합니다.

- 한국: 네이버 실시간 시세 (실패 시 Yahoo)
- 미국: Yahoo 시세 (실패 시 네이버), 프리·애프터마켓 포함
- 환율: Yahoo USD/KRW
- 장중 10~15분마다 자동 실행, `workflow_dispatch`로 즉시 실행 가능
