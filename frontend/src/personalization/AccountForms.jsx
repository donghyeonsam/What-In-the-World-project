import { useState } from 'react';
import { accountApi } from './accountApi.js';
import s from './Personalization.module.css';

export function AuthForm({ onLogin, notice }) {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState(notice || '');
  const signup = mode === 'signup';
  async function run(action) {
    setError(''); setMessage(''); setBusy(true);
    try { await action(); } catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  const submit = (event) => {
    event.preventDefault();
    if (signup && !verified) { setError('먼저 이메일 인증을 완료해 주세요.'); return; }
    if (signup && password !== confirm) { setError('비밀번호 확인이 일치하지 않습니다.'); return; }
    run(async () => {
      if (signup) {
        await accountApi.signup(email.trim(), password);
        setMode('login'); setPassword(''); setConfirm(''); setVerified(false); setSent(false);
        setMessage('회원가입이 완료되었습니다. 로그인해 주세요.');
      } else {
        await accountApi.login(email.trim(), password);
        setPassword('');
        await onLogin();
      }
    });
  };
  return <>
    <p className={s.description}>로그인하고 관심 있는 테마의 뉴스를 구독하세요.</p>
    <div className={s.tabs}>{[['login', '로그인'], ['signup', '회원가입']].map(([value, label]) => <button type="button" disabled={busy} key={value} aria-pressed={mode === value} onClick={() => { setMode(value); setError(''); setMessage(''); setPassword(''); setConfirm(''); }}>{label}</button>)}</div>
    <form className={s.form} onSubmit={submit}>
      <fieldset disabled={busy}>
        <label>이메일<input type="email" required maxLength={255} autoComplete="email" value={email} onChange={(event) => { setEmail(event.target.value); setVerified(false); setSent(false); setCode(''); }} /></label>
        {signup && <>
          <button type="button" className={s.secondary} disabled={!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) || verified} onClick={() => run(async () => { const data = await accountApi.sendCode(email.trim()); setSent(true); setMessage(`인증번호를 전송했습니다.${data?.timeLimit ? ` 유효시간 ${data.timeLimit}초.` : ''}`); })}>{verified ? '이메일 인증 완료' : sent ? '인증번호 다시 보내기' : '인증번호 보내기'}</button>
          {sent && !verified && <div className={s.inline}><label>인증번호<input value={code} maxLength={7} autoComplete="one-time-code" onChange={(event) => setCode(event.target.value)} placeholder="영문·숫자 7자리" /></label><button type="button" className={s.secondary} disabled={!/^[A-Za-z0-9]{7}$/.test(code)} onClick={() => run(async () => { await accountApi.verifyCode(email.trim(), code); setVerified(true); setMessage('이메일 인증이 완료되었습니다.'); })}>인증하기</button></div>}
        </>}
        <label>비밀번호<input type="password" required minLength={8} maxLength={72} autoComplete={signup ? 'new-password' : 'current-password'} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="8~72자" /></label>
        {signup && <label>비밀번호 확인<input type="password" required minLength={8} maxLength={72} autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} /></label>}
        <button className={s.primary} type="submit" disabled={signup && !verified}>{busy ? '처리 중…' : signup ? '회원가입' : '로그인'}</button>
      </fieldset>
      {error && <p role="alert" className={s.error}>{error}</p>}
      {message && <p role="status" className={s.message}>{message}</p>}
    </form>
  </>;
}

export function PasswordForm({ onChanged, onExpired }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault(); setError('');
    if (next !== confirm) { setError('새 비밀번호 확인이 일치하지 않습니다.'); return; }
    if (current === next) { setError('현재 비밀번호와 다른 비밀번호를 입력해 주세요.'); return; }
    setBusy(true);
    try { await accountApi.changePassword(current, next); setCurrent(''); setNext(''); setConfirm(''); onChanged(); }
    catch (err) { if (err.status === 401) onExpired(); else setError(err.message); }
    finally { setBusy(false); }
  }
  return <form className={s.form} onSubmit={submit}><p className={s.description}>비밀번호 변경 후에는 다시 로그인해야 합니다.</p><fieldset disabled={busy}>
    <label>현재 비밀번호<input type="password" required minLength={8} maxLength={72} autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} /></label>
    <label>새 비밀번호<input type="password" required minLength={8} maxLength={72} autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} placeholder="8~72자" /></label>
    <label>새 비밀번호 확인<input type="password" required minLength={8} maxLength={72} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></label>
    <button className={s.primary} type="submit">{busy ? '변경 중…' : '비밀번호 변경'}</button></fieldset>{error && <p className={s.error} role="alert">{error}</p>}
  </form>;
}
