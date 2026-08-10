import os
import httpx
from dotenv import load_dotenv

load_dotenv()

WEATHER_API_URL = os.getenv(
    "WEATHER_API_URL",
    "https://api.open-meteo.com/v1/forecast",
)


async def get_weather_data(latitude: float, longitude: float):
    """
    Fetch current weather information for a location.
    """

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": True,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            WEATHER_API_URL,
            params=params,
        )

        response.raise_for_status()

        return response.json()
