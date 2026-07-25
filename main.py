import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# 타 모듈 로드 (다음 단계에서 작성할 파일들)
from data_pipeline import fetch_realtime_data
from predictor import predict_future_bikes

app = FastAPI(
    title="따릉이 대여량 예측 API 시스템",
    description="서울시 실시간 따릉이 데이터 및 날씨 기반 ML 예측 서빙 API",
    version="1.0.0"
)

# Render <-> Vercel 간의 크로스 도메인 차단(CORS) 해제 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Vercel 배포 후 특정 URL로 제한 가능
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST 등 모든 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

@app.get("/")
async def root():
    """서버 생존 확인용 헬스체크 엔드포인트"""
    return {"status": "healthy", "message": "Seoul Bike Prediction Server is running."}

@app.get("/api/predict")
async def get_bike_prediction(
    lat: float = Query(..., description="사용자 현재 위도"),
    lon: float = Query(..., description="사용자 현재 경도")
):
    """
    프론트엔드에서 위도/경도를 받아 3시간 뒤 대여량을 예측하는 메인 API
    """
    try:
        # 1. 수집 엔진 가동 (가장 가까운 대여소 정보 및 실시간 날씨 융합 데이터 가져오기)
        station_data, weather_data = await fetch_realtime_data(lat, lon)
        
        if not station_data:
            raise HTTPException(status_code=444, detail="주변 1km 이내에 따릉이 대여소가 없습니다.")

        # 2. 예측 엔진 가동 (머신러닝 모델 스코어링)
        prediction_result = predict_future_bikes(station_data, weather_data)

        # 3. 우와 소리 나오는 최종 텍스트 결과 조립 및 반환
        return {
            "stationName": station_data["stationName"],
            "currentBikes": station_data["parkingBikeCount"],
            "predictedBikes3HoursLater": prediction_result["predictedCount"],
            "weather": {
                "temp": weather_data["temp"],
                "rain": weather_data["rain_flag"]
            },
            "analysis": prediction_result["analysis_message"],
            "alertLevel": prediction_result["alert_level"]
        }

    except Exception as e:
        # 예외 발생 시 에러 로깅 및 500 에러 반환
        raise HTTPException(status_code=500, detail=f"서버 내부 오류: {str(e)}")
