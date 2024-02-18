import axios from 'axios';
import { authRoutes } from '@/data/routes';

type ValidateTokenResponse = {
  ok: boolean;
  data?: any;
};

export const validateTokenAndObtainSession = async ({ idToken }: { idToken: string }): Promise<ValidateTokenResponse> => {
  try {
    const response = await axios.post(
      authRoutes.googleLogin,
      { token: idToken },
      {
        headers: {
          'Content-Type': 'application/json',
        },
        withCredentials: true,
      }
    );

    if (response.status !== 200) {
      throw new Error('Network response was not ok');
    }

    const responseData = await response.data;
    return { ok: true, data: responseData };
  } catch (error) {
    console.error('validateTokenAndObtainSession error:', error);
    return { ok: false };
  }
};
