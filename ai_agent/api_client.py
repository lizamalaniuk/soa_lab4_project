
import os
import requests


class APIClient:
    def __init__(self):
        self.base_url = os.getenv(
            "API_BASE_URL",
            "http://localhost:8080/api"
        ).rstrip("/")

        self.session = requests.Session()

    def request(self, method, endpoint, data=None, params=None):
        allowed_methods = {"GET", "POST", "PUT", "PATCH"}
        method = method.upper()

        if method not in allowed_methods:
            return {"error": "HTTP method is not allowed"}

        if not endpoint.startswith("/") or endpoint.startswith("//"):
            return {"error": "Invalid API endpoint"}

        try:
            response = self.session.request(
                method=method,
                url=f"{self.base_url}{endpoint}",
                json=data,
                params=params,
                timeout=10,
                allow_redirects=False
            )

            response.raise_for_status()

            if not response.content:
                return {"success": True}

            return response.json()

        except requests.RequestException as error:
            return {"error": str(error)}
        except ValueError:
            return {"error": "Invalid JSON response"}
