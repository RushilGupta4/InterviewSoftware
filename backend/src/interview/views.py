from rest_framework.views import APIView
from rest_framework.response import Response
import jwt

from .models import Interview


JWT_ALGORITHM = "HS256"


class CreateInterviewView(APIView):
    def post(self, request):
        user = request.user

        try:
            company_name = request.data["companyName"]
            job_description = request.data["jobDescription"]
        except KeyError:
            return Response({"detail": "Invalid Request"})

        interview = Interview.objects.create(
            user=user,
            company_name=company_name,
            job_description=job_description,
        )

        # create a token for the interview and user
        token = jwt.encode(
            {"interviewId": str(interview.uid)},
            user.secret_key,
            algorithm=JWT_ALGORITHM,
        )

        return Response(
            {
                "detail": "Success",
                "data": {
                    "interviewToken": token,
                    "email": user.email,
                },
            }
        )


class GetInterviewView(APIView):
    def get(self, request):
        user = request.user
        interviews = Interview.objects.order_by("-created_at").filter(user=user)
        data = [
            {
                "company_name": interview.company_name,
                "job_description": interview.job_description,
                "interviewId": interview.uid,
            }
            for interview in interviews
        ]
        return Response(data)
