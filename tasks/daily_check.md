# 종목 레이더 매일 점검 지침

이 파일은 "이슬의 종목 레이더" 예약 점검(아침 9:30)과 업데이트 버튼 작업이 따르는 지침입니다. 규칙을 바꿀 때는 이 파일만 고치면 됩니다.


시작하자마자 Bash로 `TZ=Asia/Seoul date +%Y-%m-%dT%H:%M:%S+09:00` 를 실행해 실제 현재 시각을 확인하고, 아래에서 "현재 시각"은 모두 이 값(저장 직전에 한 번 더 확인)을 씁니다.

## 가격 출처: GitHub 시세 수집기 (최우선)
사용자의 공개 저장소 kwangmin0822/stock-radar-prices 에서 GitHub Actions가 네이버(한국)·야후(미국) 실시간 시세를 받아 prices.json 에 기록합니다(장중 10~15분마다 자동). WebFetch로 읽는 시세 페이지는 하루 이상 늦은 캐시가 섞이는 것이 확인됐으므로 **가격은 prices.json 값을 씁니다.**
prices.json 형식: {updatedAt, fxUSDKRW, fxAt, KR:{"<6자리코드>":{price, change(등락률 %), at("YYYY-MM-DDTHH:MM", 한국시간), status("OPEN"|"CLOSE" 등), src}}, US:{"<티커>":{price, change, prevClose, at("...+09:00"), src, ext?:{price, at}(프리·애프터마켓)}}, missing}
가져오는 법:
a. 먼저 최신 시세를 새로 받게 합니다. mcp 도구 add_repo(owner "kwangmin0822", repo "stock-radar-prices", access "push")를 호출하고, 안내대로 /home/claude/stock-radar-prices 에 clone 합니다. 후보·보유 종목 중 tickers.json({"KR":[코드...],"US":[티커...]})에 없는 것이 있으면 추가(기존 것은 지우지 말고, KR에 "379800", "069500" 유지)해서 commit·push 합니다(push하면 수집이 자동 시작). 추가할 것이 없으면 `gh api -X POST repos/kwangmin0822/stock-radar-prices/actions/workflows/prices.yml/dispatches -f ref=main` 로 즉시 실행합니다(gh workflow/gh run 명령은 GraphQL이 막혀 있어 실패하므로 반드시 gh api REST를 씁니다). 그다음 `gh api 'repos/kwangmin0822/stock-radar-prices/actions/runs?per_page=1' --jq '.workflow_runs[0]|[.status,.conclusion,.created_at]'` 로 실행이 끝날 때까지 20초 간격으로 최대 4분 기다리고, `git -C /home/claude/stock-radar-prices pull -q` 후 prices.json 을 읽습니다.
b. add_repo나 gh가 실패하면 `git ls-remote https://github.com/kwangmin0822/stock-radar-prices refs/heads/main` 으로 최신 커밋 sha를 얻어 `curl -sS https://raw.githubusercontent.com/kwangmin0822/stock-radar-prices/<sha>/prices.json` 로 읽습니다(마지막 자동 수집 값).
c. prices.json에 없는 종목만 예전 방식(한국 https://markets.hankyung.com/stock/<코드>, 미국 https://stockanalysis.com/stocks/<티커 소문자>/ 를 WebFetch, prompt "Copy exactly as displayed, do not estimate. Return only compact JSON: {price, changePct, asOf, status}.")으로 가져오고, 보고에 "지연 시세"라고 적습니다.
변환: price = price, changePct = change, asOf = at, status: 한국은 status가 "OPEN"이면 open 아니면 closed. 미국은 at이 미국 정규장 시간(한국시간 22:30~05:00, 서머타임 해제 시 23:30~06:00) 안이면 open, 아니면 closed. 미국 ext는 참고만 하고 가격으로 쓰지 않습니다.
fxUSDKRW가 있으면 이 값을 환율로 쓰고 meta/info 의 fxUSDKRW도 이 값(소수 1자리)으로 갱신합니다.
d. 같은 저장소의 stats.json(평일 아침 6시 갱신, {updatedAt, vol:{"KR-<코드>"|"US-<티커>": 1년 변동성 %}, ma200:{같은 키: 200일 평균 종가(현지통화)}, p52:{같은 키: 52주 수익률 %}, p26:{같은 키: 6개월 수익률 %}, hi52:{같은 키: 현재가 ÷ 52주 최고 종가 × 100}, m6s:{같은 키: 최근 1달을 뺀 6개월 수익률 %}, m712:{같은 키: 12개월 전~6개월 전 수익률 %}, max21:{같은 키: 최근 21거래일 중 가장 큰 하루 상승률 %}, regime:{KR:{crash, spread}, US:{crash, spread}}, bench:{"KR-069500":[[날짜, 종가]...], "KR-379800":[[날짜, 종가]...]}})과 universe.json(평일 아침 5시 30분 갱신, 후보 목록과 지표: {updatedAt, KR:{"<코드>":{name, market, marketCap, price, sector, fin, pe, forwardPE, pb, roe, operatingMargin, debtToEquity, dividendYield, dataDate, earnDate}}, US:{"<티커>":{name, marketCap, price, sector, fin, pe, forwardPE, pb, roe, operatingMargin, debtToEquity, fcfYield, dividendYield, earnDate}}})도 a 또는 b와 같은 방법으로 읽습니다(b라면 같은 sha의 /stats.json, /universe.json).

## 1. 읽기
- ArtifactData list: collection "stocks", query.limit 1000 → 기존 종목 문서 전부(id 형식 "KR-<6자리코드>" 또는 "US-<티커>", 필드 market, ticker, nameKo, fin, sector, price, currency, active, etf, version 등).
- ArtifactData get: collection "data/users/me", doc_id "portfolio" → cash(주문가능 원화), usd(주문가능 달러, 없으면 0), holdings({id:{qty, avg(현지통화), currency, name}}). qty>0만 보유로 봅니다.
- ArtifactData get: collection "data/users/me", doc_id "alerts" (없을 수 있음) → version, peaks.
- ArtifactData get: collection "meta", doc_id "info" → fxUSDKRW(원/달러), version. collection "meta", doc_id "bench"도 get 해서 version을 확보합니다(없을 수 있음).
- ArtifactData list: collection "newsScore" → 종목별 뉴스 점수 {score, kind, at} (5단계 손절 판정에 사용).
- 위 '가격 출처' a~b로 prices.json을 읽어 둡니다(후보가 정해진 뒤 tickers.json에 없는 종목이 있으면 a를 한 번 더 해서 받아 옵니다).

## 2. 총자산과 가격 상한
총자산 = cash + usd×환율 + 보유 종목 평가액(prices.json 가격, 미국 종목은 환율로 원화 환산). 가격 상한 cap = 총자산 × 0.98 (원). 미국 종목 상한 capUSD = cap / 환율.
총자산이 1만 원 미만이면 3단계는 건너뜁니다.

## 3. 후보 종목 다시 고르기 (목록은 후보 선정에만 사용, 가격은 prices.json)
- 한국: WebFetch 하지 않습니다. universe.json의 KR 종목(시가총액 3천억 원 이상, 거래가 충분한 약 200개) 중 price <= cap×1.1 인 것 전부가 한국 후보입니다(개수 제한 없음).
- 미국: 역시 WebFetch 하지 않습니다. universe.json의 US 종목(시가총액 100억 달러 이상 약 300개) 중 price <= capUSD×1.1 인 것 전부가 미국 후보입니다.
목록 가격은 늦을 수 있으므로 여유(×1.1)를 두고 고른 뒤, 4단계에서 prices.json 가격으로 다시 판단합니다.
후보 = 한국 후보 + 미국 후보 + 현재 보유 종목 + stocks에서 etf:true인 지수 ETF 문서 전부(지수 ETF는 개별 종목의 비교 기준이라 항상 active:true로 두고 가격·ma200만 갱신합니다. 지표 대상이 아니며, 가격 상한(cap)으로 빼지도 않습니다).

## 4. 후보 종목 가격
- 각 후보의 가격은 prices.json 값(없으면 '가격 출처' c)을 씁니다.
- 가격이 cap(미국은 capUSD)을 넘으면 후보에서 뺍니다(보유 종목과 지수 ETF는 제외하지 않음).
- 기존 price와 30% 넘게 차이 나면 가격 출처 c 방식으로 한 번 확인해서 비슷할 때만 씁니다. 다르면 갱신하지 말고 보고에 적습니다.

후보별 처리:
- 이미 stocks에 있는 종목: op "update"로 {active: true, price, dayChange: changePct, priceDate: asOf의 날짜(YYYY-MM-DD), priceAt: asOf를 "YYYY-MM-DDTHH:MM" 형식으로, priceKind: status가 closed면 "close" 아니면 "intraday"} 와, stats.json에 그 종목 id가 있으면 vol과 ma200도 함께 씁니다.
- 후보의 지표는 처음 보는 종목이든 기존 종목이든 universe.json 값으로 씁니다(WebFetch 없음). 처음 보는 종목은 op "set"으로 {market, ticker(한국은 코드, 미국은 티커), nameKo: name, fin, sector, price, currency("KRW"|"USD"), marketCap, pe, forwardPE, pb, roe, debtToEquity, operatingMargin, fcfYield(한국은 null), priceChange52w: stats.json p52 값(없으면 null), priceChange26w: stats.json p26 값(없으면 null), nearHigh52: stats.json hi52 값(없으면 null), mom6s: stats.json m6s 값(없으면 null), mom12_7: stats.json m712 값(없으면 null), max21: stats.json max21 값(없으면 null), dividendYield, dataDate(한국만), earnDate(없으면 null), dayChange, priceDate, priceAt, priceKind, vol, ma200, active: true}, 기존 종목은 update에 지표 필드(pe, forwardPE, pb, roe, debtToEquity, operatingMargin, fcfYield, priceChange52w, priceChange26w, nearHigh52, mom6s, mom12_7, max21, dividendYield, earnDate, marketCap, sector, fin, 한국은 dataDate)를 같이 넣습니다. universe.json에서 값이 null인 지표는 기존 값을 지우지 말고 그대로 둡니다(earnDate는 null이면 null로 씁니다).
- universe.json에 없는 보유 종목·custom 종목은 지표를 건드리지 않고 가격만 갱신합니다.
  - fin=true면 debtToEquity, operatingMargin, fcfYield 는 null.
  - 이름에 "ADR"이 있는 등 미국에 상장된 외국 기업이면(처음 볼 때 한 번, 아는 정보로 판단) country(본사 국가 ISO 2자리, 예 "BR","IN","JP","GB")를 쓰고, 정부·국영기관이 최대주주면 stateOwned:true도 씁니다(페이지가 신흥국 감점·국영기업 매수 제외에 사용).
- custom:true 이고 pe·roe 같은 지표가 비어 있는 종목(사용자가 직접 입력한 종목)은 statistics 페이지(한국 https://stockanalysis.com/quote/krx/<코드>/statistics/, 미국 https://stockanalysis.com/stocks/<티커 소문자>/statistics/)를 prompt "Return only compact JSON: {name, marketCap, pe, forwardPE, pb, roe, debtToEquity, operatingMargin, fcfYield, priceChange52w, dividendYield, dataDate}. Percent values as numbers (e.g. 12.3). Use null if missing." 로 가져와 update 합니다(market, ticker, nameKo, currency는 바꾸지 않음).
- stocks에 있지만 이번 후보가 아니고 보유 중도 아니고 etf:true도 아닌 종목: op "update"로 {active: false} 만 씁니다(지우지 않음). 단, prices.json에 가격이 있으면 price·dayChange·priceDate·priceAt·priceKind(와 stats.json의 vol·ma200)는 같이 갱신해 둡니다.
모든 쓰기는 ArtifactData batch(한 배치 최대 50개)로, 기존 문서에는 1단계에서 읽은 version을 if_version으로 넣습니다.

## 5. 보유 종목 매도 판정 (페이지와 같은 기준, 가격은 현지통화)
- ret = 현재가 / avg - 1, peak = max(avg, 현재가, 기존 peaks[id].price), fromPeak = 현재가 / peak - 1
**미국 종목(id가 "US-")은 1·2·6번(손절, 이익 보호, 손절선 근접)을 적용하지 않습니다** — 2026-11-11 실제 계좌 재현 테스트(pit_us7)에서 손절 없이 들고 간 쪽이 15~18% 더 많이 남음. 미국 종목은 순위 하락 교체로만 정리됩니다(페이지가 계산). 한국 종목은 모두 정리 대상이므로 level "sell", reason "한국 종목 정리 · 판 돈은 미국 추세 종목으로".
위에서부터 먼저 걸리는 하나:
1. 손절(한국만): ret <= -12% 이면 예외 없이 매도 → level "sell", reason "손절: 매입가 대비 X% (기준 -12%) · (이유)". (이유)는 악재 뉴스(newsScore 컬렉션의 그 종목 문서가 score < 0 이고 아직 반영 기간 안 — earnings/policy는 60일, news는 7일)면 "악재 뉴스 반영 중", 현재가 < ma200×1.05 면 "200일 평균선(X) 근처", 그 밖에는 "규칙대로 정리". (과거 검증은 예외 없는 손절로 했으므로 예외를 두지 않음. 신호는 종가 기준이라 다음 날 실제 체결가는 더 낮을 수 있음)
2. 이익 보호(한국만): peak >= avg×1.10 이고 fromPeak <= -15% → level "sell", reason "이익 보호: 최고가 대비 X% 하락 (수익 Y%일 때 정리)"
3. 적자 전환: roe < 0 → level "sell", reason "적자 전환 (ROE X%)"
4. 추세 꺾임: 현재가 < ma200 → level "watch", reason "200일 평균선(X) 아래로 내려옴 · 추세가 꺾여 추세 점수를 낮춤"
5. 급락: dayChange <= -7 → level "watch", reason "하루 X% 급락 · 뉴스 확인 필요"
6. 손절선 근접(한국만): ret <= -6% → level "watch", reason "매입가 대비 X% · 손절선(-12%)에 가까움"
숫자는 소수 첫째 자리까지.

## 6. 저장 (모든 시각은 저장 직전에 date로 다시 확인한 실제 현재 시각)
- collection "data/users/me", doc_id "alerts" 에 set(기존 문서가 있으면 if_version): {date: 오늘 YYYY-MM-DD(한국시간), checkedAt: 현재 시각, checked: 보유 종목 수, items: [{id, name, level, reason, ret, fromPeak}], peaks: 보유 종목 전부의 {id:{price: peak, date}} (팔고 없어진 종목은 빼기)}
- collection "data/users/me", doc_id "log-YYYY-MM-DD"(오늘)에 set(있으면 덮어쓰기): {date, cash, usd, holdings: 보유 종목별 {qty, avg, price, ret}, items, totalKRW: 총자산, universe: 이번 후보 수}
- collection "meta", doc_id "bench" 를 set(있으면 get 해서 if_version): stats.json의 bench에서 "KR-069500"과 "KR-379800" 둘 다 있는 날짜만 최근 400개로 {dates:[날짜...], k200:[KR-069500 종가...], sp500:[KR-379800 종가...], updatedAt: stats.json updatedAt} (페이지 '기록' 탭의 지수 비교에 사용. 큰 배열이므로 Bash로 JSON 파일을 만든 뒤 ArtifactData set의 file_path로 넘기세요).
- collection "meta", doc_id "info" 를 update(if_version): {regime: stats.json의 regime 그대로(없으면 넣지 않음), universeAt: 현재 시각, universeCap: cap, count: active 종목 수, fxUSDKRW(prices.json 값이 있으면), priceSource: "github:kwangmin0822/stock-radar-prices", pricesAt: prices.json의 updatedAt}
portfolio 문서와 tx 기록은 절대 수정하지 마세요. 실제 주문도 하지 않습니다.

## 7. 보고 (한국어, 짧게)
- 매도 신호가 있으면 첫 줄 "[매도 신호 N건]", 종목별 이름·사유·현재 수익률 한 줄씩, 그리고 "페이지 '내 계좌' 탭에서 확인하고, 매도했다면 체결 기록을 남겨 주세요."
- 없으면 첫 줄 "[매도 신호 없음] 보유 N종목 점검 완료", 주의 종목이 있을 때만 한 줄씩.
- 보유 종목별 "이름 현재가 (기준 시각, 장중/종가)" 한 줄씩.
- "총자산 X원 기준 후보 N종목(한국 a · 미국 b, 새로 추가 c)" 한 줄.
- (원화+달러) 예수금이 총자산의 10% 이상이면 "예수금이 쉬고 있어요. 매수 추천과 필요한 환전 금액이 페이지에 갱신돼 있습니다." 한 줄.
- 시세 수집기 실행에 실패했거나 지연 시세를 쓴 종목이 있으면 마지막에.
- 마지막 줄: "규칙에 따른 알림이며 투자 자문이 아닙니다."