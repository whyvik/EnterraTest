from typing import Optional
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from fastapi_cache.backends.memory import InMemoryCacheBackend
import os
import httpx
import json

from pydantic import BaseModel

load_dotenv()
API_KEY = os.environ.get("API_KEY")
BASE_URL = os.environ.get("BASE_URL")

app = FastAPI()
cache = InMemoryCacheBackend()

# Время жизни кэша 5 минут
cache_ttl = 60 * 5


class CitySchema(BaseModel):
    city: Optional[str] = None
    parameters: Optional[str] = None


class CitiesSchema(BaseModel):
    cities: Optional[list] = None
    parameters: Optional[str] = None


def find_param(data, param):
    if isinstance(data, dict):
        if param in data:
            return data[param]
        for key, value in data.items():
            data_value = find_param(value, param)
            if data_value is not None:
                return data_value
    elif isinstance(data, list):
        for item in data:
            data_value = find_param(item, param)
            if data_value is not None:
                return data_value
    return None


async def get_weather(city: str, parameters: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}?q={city}&appid={API_KEY}"
        )
        data_json = {'city': city}
        for param in list(parameters.split(' ')):
            data_json[param] = find_param(json.load(response), param)
        return data_json


@app.post('/weather/city')
async def get_city_weather(request: CitySchema):
    cached_data = await cache.get(request.city)
    if cached_data:
        return cached_data
    try:
        weather_data = await get_weather(request.city, request.parameters)
        await cache.set(request.city, weather_data, ttl=cache_ttl)
        return weather_data
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail="Сервис OpenWeather недоступен")


@app.post('/weather/cities')
async def get_cities_weather(request: CitiesSchema):
    weather_data = {}
    errors = {}

    for city in request.cities:
        try:
            data = await cache.get(city)
            if data is None:
                data = await get_weather(city, request.parameters)
                await cache.set(city, data, ttl=cache_ttl)
            weather_data[city] = data
        except httpx.HTTPError as e:
            errors[city] = "Сервис OpenWeather недоступен"

    return {"weather_data": weather_data, "errors": errors}
