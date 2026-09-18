import { request } from '../data/api.js';
const post = (path, body) => request(path, { method: 'POST', body, allowEmpty: true });
export const accountApi = {
  me: (signal) => request('/users/me', { signal }),
  login: (email, password) => post('/auth/login', { email, password }),
  ssafyLogin: (code) => post('/auth/ssafy', { code }),
  logout: () => post('/auth/logout'),
  signup: (email, password) => post('/auth/signup', { email, password }),
  sendCode: (email) => post('/auth/email/send', { email }),
  verifyCode: (email, code) => post('/auth/email/verify', { email, code }),
  sendPasswordResetCode: (email) => post('/auth/password/email/send', { email }),
  verifyPasswordResetCode: (email, code) => post('/auth/password/email/verify', { email, code }),
  resetPassword: (newPassword) => post('/auth/password/reset', { newPassword }),
  changePassword: (currentPassword, newPassword) => request('/users/password', {
    method: 'PATCH', body: { currentPassword, newPassword }, allowEmpty: true,
  }),
  withdraw: (password) => request('/users/withdraw', {
    method: 'PATCH', body: { password }, allowEmpty: true,
  }),
  // 관심 테마는 계정별로 서버(user_interest_theme)에 저장한다.
  interestThemes: (signal) => request('/users/me/interests/themes', { signal }),
  addInterestTheme: (themeId) => post('/users/me/interests/themes', { themeId }),
  removeInterestTheme: (themeId) => request(`/users/me/interests/themes/${encodeURIComponent(themeId)}`, {
    method: 'DELETE', allowEmpty: true,
  }),
};
