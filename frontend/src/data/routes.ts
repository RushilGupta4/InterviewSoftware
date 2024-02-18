const baseUrl = process.env.NEXT_PUBLIC_BASE_BACKEND_URL;

export const authRoutes = {
  googleLogin: `${baseUrl}/auth/login/google/`,
  verifyToken: `${baseUrl}/auth/token/verify/`,
};
