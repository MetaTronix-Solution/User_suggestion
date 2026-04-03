# User Suggestion API

A FastAPI-based REST API for computing personalized user recommendations using hybrid recommendation algorithms combining text similarity, graph-based scoring, collaborative filtering, and interest overlap.

## Features

- **Hybrid Recommendations**: Combines multiple algorithms for better accuracy
  - Text similarity (bio, education, occupation, hobbies)
  - Graph-based scoring (mutual connections)
  - Interest overlap
  - Collaborative filtering (shared followers)
- **RESTful API endpoints**: Easy integration with frontend and other services
- **Configurable result size**: Get top N suggestions
- **Detailed scoring breakdown**: See how each recommendation score is calculated
- **Auto-generated API documentation**: Interactive Swagger UI at /docs

## Prerequisites

- Python 3.8+
- PostgreSQL database (with social_db schema)
- pip or conda for package management

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/innovator.git
cd innovator
```

### 2. Create Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the example environment file and update with your database credentials:

```bash
cp .env.example .env
```

Edit `.env` with your database connection details:

```
DB_HOST=your_host
DB_PORT=5436
DB_NAME=social_db
DB_USER=your_username
DB_PASSWORD=your_password
```

## Running the API

### Development Server

```bash
python api_app.py
```

Or with auto-reload:

```bash
uvicorn api_app:app --reload
```

The API will be available at `http://localhost:5000`

Interactive API docs: `http://localhost:5000/docs`

### Production Deployment

For production, use uvicorn with multiple worker processes:

```bash
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker api_app:app
```

## API Endpoints

### 1. Health Check

**GET** `/health`

Check if the API is running.

**Response:**
```json
{
  "status": "healthy",
  "message": "API is running"
}
```

### 2. Get Suggestions

**GET** `/api/suggestions/<target_user_id>`

Get top recommendations for a specific user.

**Query Parameters:**
- `top_n` (int, optional): Number of suggestions to return. Default: 5. Max: 50

**Example:**
```
GET /api/suggestions/bd4cade0-3abd-45e5-a1c0-30f8c64681cd?top_n=10
```

**Response:**
```json
{
  "target_user_id": "bd4cade0-3abd-45e5-a1c0-30f8c64681cd",
  "count": 5,
  "suggestions": [
    {
      "user_id": "user-id-1",
      "username": "john_doe",
      "full_name": "John Doe",
      "score": 0.85,
      "breakdown": {
        "text_score": 0.80,
        "graph_score": 0.90,
        "interest_score": 0.85,
        "collab_score": 0.75
      }
    },
    ...
  ]
}
```

### 3. Get Detailed Suggestions

**GET** `/api/suggestions/<target_user_id>/detailed`

Same as above but includes formatted percentage breakdowns for easier frontend rendering.

**Response:**
```json
{
  "target_user_id": "bd4cade0-3abd-45e5-a1c0-30f8c64681cd",
  "count": 5,
  "suggestions": [
    {
      "user_id": "user-id-1",
      "username": "john_doe",
      "full_name": "John Doe",
      "score": 0.85,
      "breakdown": {
        "text_score": 0.80,
        "graph_score": 0.90,
        "interest_score": 0.85,
        "collab_score": 0.75,
        "visual_score": {
          "text": "80.0%",
          "graph": "90.0%",
          "interest": "85.0%",
          "collab": "75.0%"
        }
      }
    }
  ]
}
```

### 4. Get API Stats

**GET** `/api/stats`

Get API version and endpoint information.

**Response:**
```json
{
  "api_version": "1.0.0",
  "endpoints": [
    "/health",
    "/api/suggestions/<user_id>",
    "/api/suggestions/<user_id>/detailed",
    "/api/stats"
  ],
  "docs": "/docs"
}
```

## Scoring Algorithm

The recommendation score is a weighted combination of four components:

| Component | Weight | Description |
|-----------|--------|-------------|
| Text Similarity | 30% | Similarity of bio, education, occupation, hobbies |
| Graph Score | 30% | Common connections via following relationships |
| Interest Score | 20% | Overlap in user interests/categories |
| Collaborative | 20% | Shared followers (collaborative filtering proxy) |

**Final Score = 0.3 × Text + 0.3 × Graph + 0.2 × Interest + 0.2 × Collab**

## Integration Examples

### JavaScript/Node.js

```javascript
const axios = require('axios');

const API_URL = 'http://localhost:5000/api';
const userId = 'bd4cade0-3abd-45e5-a1c0-30f8c64681cd';

async function getSuggestions() {
  try {
    const response = await axios.get(`${API_URL}/suggestions/${userId}?top_n=5`);
    console.log(response.data);
  } catch (error) {
    console.error('Error fetching suggestions:', error);
  }
}

getSuggestions();
```

### Python

```python
import requests

API_URL = 'http://localhost:5000/api'
user_id = 'bd4cade0-3abd-45e5-a1c0-30f8c64681cd'

response = requests.get(f'{API_URL}/suggestions/{user_id}', params={'top_n': 5})
suggestions = response.json()
print(suggestions)
```

### cURL

```bash
curl -X GET "http://localhost:5000/api/suggestions/bd4cade0-3abd-45e5-a1c0-30f8c64681cd?top_n=5"
```

## Project Structure

```
innovator/
├── api_app.py                          # Main Flask application
├── app.py                              # Legacy/utility app
├── abc.py                              # Utility script
├── requirements.txt                    # Python dependencies
├── .env.example                        # Environment variables template
├── .gitignore                          # Git ignore rules
├── README.md                           # This file
└── utils/
    ├── suggestions.py                  # Core recommendation logic
    ├── all_users_attributes_v3.csv    # User data cache
    └── ...
```

## Troubleshooting

### Database Connection Error
- Verify database credentials in `.env`
- Ensure PostgreSQL server is running
- Check database host and port are correct

### Missing Dependencies
```bash
pip install -r requirements.txt
```

### Port Already in Use
Change the port in `api_app.py`:
```python
app.run(debug=True, host='0.0.0.0', port=5001)  # Change port here
```

## Performance Considerations

- First request may be slow (model loading and CSV parsing)
- Results are cached in CSV files for faster subsequent requests
- Consider implementing request caching for frequently requested users

## Future Enhancements

- [ ] Add authentication and rate limiting
- [ ] Implement caching layer (Redis)
- [ ] Add user profiles endpoint
- [ ] Create WebSocket for real-time suggestions
- [ ] Add CSV data refresh endpoint
- [ ] Implement pagination for large result sets
- [ ] Add request logging and monitoring

## Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Commit changes: `git commit -am 'Add new feature'`
3. Push branch: `git push origin feature/your-feature`
4. Create Pull Request

## License

[Your License Here]

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review existing GitHub issues
3. Create a new issue with detailed information

## Team Information

- **Project**: Innovator - User Recommendation System
- **Repository**: [GitHub Link](https://github.com/YOUR_USERNAME/innovator)
- **API Version**: 1.0.0
