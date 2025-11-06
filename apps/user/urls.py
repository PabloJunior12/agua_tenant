from rest_framework import routers
from django.urls import path
from .views import LoginView, LogoutView, ProtectedView, MeView,RucApiView, DniApiView, UserViewSet, ModuleViewSet, UserPermissionViewSet

router = routers.DefaultRouter()
router.register("users", UserViewSet)
router.register('modules', ModuleViewSet)
router.register('user-permissions', UserPermissionViewSet)


urlpatterns = [

    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('protected/', ProtectedView.as_view(), name='protected'),
    path('ruc/<str:number>', RucApiView.as_view(), name='user-ruc'),
    path('dni/<str:number>', DniApiView.as_view(), name='user-dni'),
    path('me/', MeView.as_view(), name='me'),

] + router.urls