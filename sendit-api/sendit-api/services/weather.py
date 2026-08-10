import httpx
import os


async def get_weather(latitude: float, longitude: float):
    url = os.getenv(
        "WEATHER_API_URL",
        "https://api.open-meteo.com/v1/forecast"
    )

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": True,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        response.raise_for_status()

        return response.json()
