# 📡 SILO API Quickstart Guide

This file summarizes how to interact with the SILO API to download weather data for use in CropForecaster.

---

## 🔗 Base URL

```
https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php
```

---

## ✅ Required Parameters

| Param    | Example         | Description                          |
|----------|-----------------|--------------------------------------|
| `station`| 040241          | BoM station number (e.g., Clare SA)  |
| `start`  | 20250901        | Start date (YYYYMMDD)                |
| `finish` | 20250906        | End date (YYYYMMDD)                  |
| `format` | csv             | Preferred output format              |
| `comment`| RXN             | Variable(s) (e.g., R, X, N)          |
| `username`| your@email.com | Required (for usage tracking)        |

---

## 🌡️ Variable Codes (`comment` param)

| Code | Variable                    | CropForecaster Usage        |
|------|-----------------------------|-----------------------------|
| R    | Rainfall (mm)               | ✅ Harvest rain risk        |
| N    | Minimum temperature (°C)    | ✅ Frost event detection    |
| X    | Maximum temperature (°C)    | ✅ Heat stress monitoring   |
| V    | Vapour pressure (hPa)       | Future: humidity analysis   |
| D    | Solar radiation (MJ/m²)     | Future: crop modeling       |
| E    | Class A pan evaporation     | Future: water balance       |

**For CropForecaster MVP**: Use `comment=RXN` (rainfall + min/max temps)

---

## 📥 Example API Calls

### Daily Data (Single Station)
```
https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php?
station=040241&
start=20250906&
finish=20250906&
format=csv&
comment=RXN&
username=your@email.com
```

### Historical Range (Validation)
```
https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php?
station=040241&
start=20240901&
finish=20240906&
format=json&
comment=RXN&
username=your@email.com
```

---

## 🐍 Python Implementation Examples

### Simple CSV Request
```python
import pandas as pd
from datetime import datetime, timedelta

def get_daily_weather(station_id, date_str, email):
    """Get daily weather for single station"""
    url = f"https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php?station={station_id}&start={date_str}&finish={date_str}&format=csv&comment=RXN&username={email}"
    return pd.read_csv(url)

# Get yesterday's data
yesterday = (datetime.now() - timedelta(1)).strftime('%Y%m%d')
data = get_daily_weather('040241', yesterday, 'your@email.com')
```

### JSON Request with Error Handling
```python
import requests
import time

def get_weather_data_robust(station_id, start_date, end_date, email, max_retries=3):
    """Robust API call with retries for production use"""
    url = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php"
    params = {
        'station': station_id,
        'start': start_date,
        'finish': end_date,
        'format': 'json',
        'comment': 'RXN',
        'username': email
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(2 ** attempt)  # Exponential backoff
```

---

## 🚨 Important Notes for Production

### Rate Limiting
- **No official rate limits** but be respectful
- Recommended: **1-2 requests per second max**
- Use batch date ranges when possible (not single-day calls)

### Data Quality Flags
SILO data includes quality codes:
- **0**: Actual observation
- **15**: Interpolated from nearby stations  
- **35**: Long-term average substitution

Filter by quality code if needed for critical applications.

### Station Coverage
- **2000+ stations** across Australia
- Not all stations have complete daily data
- Some stations may be discontinued
- Verify station activity before production deployment

---

## 🔧 CropForecaster Integration Checklist

- [ ] Email address configured in environment variables
- [ ] Station list filtered for Australian wheatbelt regions
- [ ] Daily automation scheduled (cron/task scheduler)
- [ ] Error handling for API timeouts/failures
- [ ] Data validation for missing values
- [ ] Quality code filtering implemented
- [ ] Performance testing for 2000+ station queries

---

## 🧠 Tips & Best Practices

### Performance Optimization
- **Batch requests**: Use date ranges instead of daily calls
- **Concurrent requests**: Use threading/async for multiple stations
- **Caching**: Store recent data locally to reduce API calls
- **Compression**: Use `format=json` for smaller payloads

### Error Handling
- **Timeout handling**: Set reasonable timeouts (30+ seconds)
- **Retry logic**: Exponential backoff for failed requests  
- **Graceful degradation**: Continue processing if some stations fail
- **Logging**: Track API response times and failures

### Data Validation
- **Range checks**: Min temp < Max temp, Rainfall >= 0
- **Missing data**: Handle NaN values appropriately
- **Quality flags**: Filter low-quality observations if needed
- **Station validation**: Verify active stations periodically

---

## 📎 See Also

- **Full API documentation**: `docs/Logpaddock_SILO_API_Reference.pdf`
- **Event detection thresholds**: `prd.md` (frost/heat/rain logic)
- **Project task management**: `task_manager.md`
- **System architecture**: `CLAUDE.md`