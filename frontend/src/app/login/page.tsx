// app/page/login.page.tsx
'use client';

import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';
import { validateTokenAndObtainSession } from '@/utils/sdk'; // Adjust the path as needed

const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || '';

const Login = () => {
  const onSuccess = async (response: any) => {
    const idToken = response.credential; // The API response structure might be different

    try {
      const resp = await validateTokenAndObtainSession({ idToken });
      if (resp.ok) {
        console.log('Login successful:');
      } else {
        console.error('Failed to log in:');
      }
    } catch (error) {
      console.error('Login error:', error);
    }
  };

  return (
    <GoogleOAuthProvider clientId={googleClientId}>
      <div>
        <h1>Welcome to our Demo App!</h1>
        <GoogleLogin onSuccess={onSuccess} onError={() => console.error('Login Failed')} />
      </div>
    </GoogleOAuthProvider>
  );
};

export default Login;
