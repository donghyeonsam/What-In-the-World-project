import { useState } from 'react';
import { request } from '../data/api.js';
import Icon from './Icon.jsx';
import { Source } from './UI.jsx';

export default function Auth({ mode, onSuccess }) {
  const [signup, setSignup] = useState(false), [email, setEmail] = useState(''), [password, setPassword] = useState(''), [code, setCode] = useState('');
  const [sent, setSent] = useState(false), [verified, setVerified] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('');
  async function run(action) { setError(''); setMessage(''); setBusy(true); try { await action(); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  const send = () => run(async () => { if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('올바른 이메일을 입력해 주세요.'); if (mode === 'live') await request('/auth/email/send', { method: 'POST', body: { email } }); setSent(true); setVerified(false); setMessage(mode === 'demo' ? '데모 인증번호는 AB12345입니다. 실제 이메일은 전송되지 않습니다.' : '인증번호를 전송했습니다. 5분 안에 입력해 주세요.'); });
  const verify = () => run(async () => { if (mode === 'live') await request('/auth/email/verify', { method: 'POST', body: { email, code } }); else if (code.trim().toUpperCase() !== 'AB12345') throw new Error('데모 인증번호 AB12345를 입력해 주세요.'); setVerified(true); setMessage('이메일 인증을 완료했습니다.'); });
  const submit = e => { e.preventDefault(); run(async () => {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('올바른 이메일을 입력해 주세요.');
    if (password.length < 8 || password.length > 72) throw new Error('비밀번호는 8~72자로 입력해 주세요.');
    if (signup && !verified) throw new Error('먼저 이메일 인증을 완료해 주세요.');
    if (mode === 'live') {
      await request(signup ? '/auth/signup' : '/auth/login', { method: 'POST', body: { email, password } });
      if (signup) { setSignup(false); setPassword(''); setMessage('가입이 완료되었습니다. 로그인해 주세요.'); return; }
    }
    onSuccess({ email, demo: mode === 'demo' });
  }); };
  return <div className="auth-body"><div className="auth-mark"><Icon name="globe" size={32}/></div><Source demo={mode === 'demo'}/><h2>{signup ? '나만의 세계를 만들어 보세요' : '다시 만나 반가워요'}</h2><p>관심 있는 이슈를 저장하고,<br/>세계의 다양한 시선을 이어서 읽으세요.</p><div className="tabs"><button className={!signup ? 'active' : ''} onClick={() => { setSignup(false); setError(''); setMessage(''); }}>로그인</button><button className={signup ? 'active' : ''} onClick={() => { setSignup(true); setError(''); setMessage(''); }}>회원가입</button></div><form onSubmit={submit}><label>이메일<input required type="email" value={email} onChange={e => { setEmail(e.target.value); setVerified(false); setSent(false); }} autoComplete="email" placeholder="you@example.com"/></label>{signup && <><button type="button" className="button secondary full" onClick={send} disabled={busy || verified}>{verified ? '이메일 인증 완료' : sent ? '인증번호 다시 보내기' : '인증번호 보내기'}</button>{sent && !verified && <div className="verification"><label>인증번호<input value={code} onChange={e => setCode(e.target.value)} placeholder="7자리 인증번호" maxLength={7}/></label><button type="button" className="button secondary" onClick={verify} disabled={busy}>확인</button></div>}</>}<label>비밀번호<input required type="password" minLength={8} maxLength={72} value={password} onChange={e => setPassword(e.target.value)} autoComplete={signup ? 'new-password' : 'current-password'} placeholder={mode === 'demo' ? '데모용 임의의 8자 이상 입력' : '8~72자'}/></label>{error && <p className="form-error" role="alert">{error}</p>}{message && <p className="form-message" role="status">{message}</p>}<button className="button primary full" disabled={busy}>{busy ? '처리 중…' : signup ? '가입하기' : '로그인'}<Icon name="arrow" size={17}/></button></form><p className="auth-note">{mode === 'demo' ? '데모 로그인은 계정을 생성하거나 비밀번호를 저장하지 않습니다. 관심사와 저장 기사는 이 브라우저에만 보관됩니다.' : '기존 인증 API에 연결합니다. 관심사·저장 기능은 별도의 브라우저 데모이며, 새로고침 후 실제 계정은 다시 로그인해야 합니다.'}</p></div>;
}
