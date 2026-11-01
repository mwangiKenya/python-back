from functools import wraps
from django.core import signing
from django.http import JsonResponse
from api.models import Users
SALT = "agency-auth"
def make_token(user):
    return signing.dumps({"id": user.id}, salt=SALT)
def agency_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            token = request.META.get("HTTP_AUTHORIZATION", "").split(" ", 1)[1]
            user = Users.objects.get(id=signing.loads(token, salt=SALT, max_age=43200)["id"])
        except Exception:
            return JsonResponse({"error": "Unauthorized"}, status=401)
        if user.agency is None:
            return JsonResponse({"error": "Forbidden"}, status=403)
        request.auth_user = user
        request.agency = user.agency
        return view(request, *args, **kwargs)
    return wrapper
def admin_required(view):
    @agency_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.auth_user.role != "admin":
            return JsonResponse({"error": "Forbidden"}, status=403)
        return view(request, *args, **kwargs)
    return wrapper