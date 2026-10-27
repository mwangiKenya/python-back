from django.urls import path
from . import views
urlpatterns = [
    path('register_user/', views.register_user,name='register_user'),
    path('users_login/', views.users_login,name='users_login'),
    path('update_employee/<int:emp_id>/', views.update_employee,name='update_employee'),
    path('list_employees/', views.list_employees, name='list_employees'),
    path('delete_employee/<int:emp_id>/', views.delete_employee),
    path("change_password/", views.change_password, name="change_password"),
    path('new_user/', views.new_user, name='new_user'),
    path('delete_user/<int:user_id>/', views.delete_user, name='delete_user'),
    path('update_user/<int:user_id>/', views.update_user, name='update_user'),
    path(
        "update_all_users/",
        views.update_all_users,
        name="update_all_users",
        ),
        path(
            "update_all_bill_phones/",
            views.update_all_bill_phones,
            name="update_all_bill_phones",
        ),
    path('water_users/', views.water_users, name='water_users'),
]