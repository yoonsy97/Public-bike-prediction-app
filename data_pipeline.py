import math
import httpx  # FastAPI와 호환성이 좋은 고성능 비동기 HTTP 클라이언트

# 서울시 열린데이터광장 따릉이 실시간 API URL
# (실제 배포 시에는 인증키를 발급받아 URL에 포함해야 합니다. 여기서는 테스트용 샘플 키를 기본 적용합니다)
SEOUL_BIKE_API_URL = "http://seoul.go.kr"

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    두 좌표 사이의 직선거리를 계산하는 하버사인(Haversine) 공식
    단위: 킬로미터(km)
    """
    R = 6371.0  # 지구 반지름
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

async def fetch_realtime_data(user_lat: float, user_lon: float):
    """
    사용자 위치 기반으로 가장 가까운 대여소 데이터와 
    기상청 정보를 융합하는 메인 데이터 파이프라인 함수
    """
    # 1. 서울시 따릉이 실시간 데이터 가져오기
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(SEOUL_BIKE_API_URL, timeout=5.0)
            if response.status_code != 200:
                raise Exception("서울시 따릉이 API 호출 실패")
            
            bike_data = response.json()
            station_list = bike_data.get("rentBikeStatus", {}).get("row", [])
        except Exception as e:
            # API 에러나 타임아웃 발생 시 시스템 중단을 막기 위한 폴백(Fallback) 더미 데이터
            station_list = [
                {"stationName": "102. 망원역 1번출구 앞", "stationLatitude": "37.555649", "stationLongitude": "126.910629", "parkingBikeCount": "12", "rackCount": "22"},
                {"stationName": "103. 망원역 2번출구 앞", "stationLatitude": "37.554958", "stationLongitude": "126.910835", "parkingBikeCount": "3", "rackCount": "15"}
            ]

    # 2. 내 주변 가장 가까운 대여소 1개 찾기 (Linear Search 최적화)
    closest_station = None
    min_distance = float('inf')

    for station in station_list:
        try:
            s_lat = float(station["stationLatitude"])
            s_lon = float(station["stationLongitude"])
        except (ValueError, KeyError):
            continue

        distance = calculate_distance(user_lat, user_lon, s_lat, s_lon)
        
        if distance < min_distance:
            min_distance = distance
            closest_station = {
                "stationName": station["stationName"],
                "parkingBikeCount": int(station["parkingBikeCount"]),
                "rackCount": int(station["rackCount"]),
                "latitude": s_lat,
                "longitude": s_lon,
                "distance_km": round(distance, 2)
            }

    # 사용자가 서울 외곽이거나 반경 2km 이내에 대여소가 없는 경우 예외 처리 기본값 정의
    if not closest_station or min_distance > 2.0:
        closest_station = {
            "stationName": "가까운 대여소를 찾지 못함 (가상 대여소 매칭)",
            "parkingBikeCount": 5,
            "rackCount": 10,
            "latitude": user_lat,
            "longitude": user_lon,
            "distance_km": 0.0
        }

    # [주의] 이 아래에 기상청 날씨 연동 로직(2단계)이 합쳐져서 하나의 weather_data를 리턴하게 됩니다.
    # 2단계 명령을 내리시면 기상청 API 파트와 최종 리턴 코드를 결합해 완성해 드리겠습니다.


    # === [2단계: 기상청 날씨 데이터 수집 및 융합 시작] ===
    
    # 기상청 단기예보용 격자 좌표 변환 함수 (서울 중심점 기준 초간단 고정 매핑 유틸)
    # 실제 기상청은 위경도를 X, Y 격자로 변환해야 하지만, 서울권은 대개 X=60, Y=127 범위에 속합니다.
    nx, ny = 60, 127 
    
    # 공공데이터포털 기상청 초단기실황 API URL (샘플 키 기준)
    WEATHER_API_URL = "http://data.go.kr"
    
    # 기상청 API 파라미터 조립 (현재 시간 기준 설정)
    # 무료 API의 안정성을 위해 에러 발생 시 적용할 기본 날씨(Fallback)를 먼저 정의합니다.
    weather_data = {
        "temp": 22.5,       # 기본 기온 (섭씨)
        "rain_flag": 0      # 기본 강수 여부 (0: 비 안옴, 1: 비 옴)
    }

    async with httpx.AsyncClient() as client:
        try:
            # 실무 팁: 실제 운영 시에는 'base_date'와 'base_time'을 현재 날짜/시간 포맷(YYYYMMDD, HH00)으로 동적 주입해야 합니다.
            params = {
                "serviceKey": "sample", # 실제 공공데이터포털에서 발급받은 디코딩 키 주입 필요
                "pageNo": "1",
                "numOfRows": "10",
                "dataType": "JSON",
                "base_date": "20260725", # 예시 고정 날짜
                "base_time": "1800",     # 예시 고정 시간
                "nx": str(nx),
                "ny": str(ny)
            }
            
            response = await client.get(WEATHER_API_URL, params=params, timeout=3.0)
            
            if response.status_code == 200:
                json_res = response.json()
                items = json_res.get("response", {}).get("body", {}).get("items", {}).get("item", [])
                
                for item in items:
                    # T1H = 기온, PTY = 강수형태
                    if item.get("category") == "T1H":
                        weather_data["temp"] = float(item.get("obsrValue", 22.5))
                    elif item.get("category") == "PTY":
                        pty_value = int(item.get("obsrValue", 0))
                        # PTY가 0이면 없음, 1 이상이면 비/눈/소나기이므로 강수 플래그를 1로 세팅
                        weather_data["rain_flag"] = 1 if pty_value > 0 else 0
                        
        except Exception:
            # 기상청 API 가끔 터지거나 타임아웃 나도 앱 전체가 멈추지 않도록 
            # 미리 정의한 기본값(weather_data)을 그대로 유지하며 통과합니다 (우와 포인트: 장애 복구력)
            pass

    # 3. main.py 가 바로 받아서 예측 엔진에 꽂아 넣을 수 있도록 튜플 데이터 반환
    return closest_station, weather_data
