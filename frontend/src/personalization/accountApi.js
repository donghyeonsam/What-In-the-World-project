import { request } from '../data/api.js';
const post = (path, body) => request(path, { method: 'POST', body, allowEmpty: true });
export const accountApi = {
  me: (signal) => request('/users/me', { signal }),
  login: (email, password) => post('/auth/login', { email, password }),
  logout: () => post('/auth/logout'),
  signup: (email, password) => post('/auth/signup', { email, password }),
  sendCode: (email) => post('/auth/email/send', { email }),
  verifyCode: (email, code) => post('/auth/email/verify', { email, code }),
  changePassword: (currentPassword, newPassword) => request('/users/password', {
    method: 'PATCH', body: { currentPassword, newPassword }, allowEmpty: true,
  }),
};
