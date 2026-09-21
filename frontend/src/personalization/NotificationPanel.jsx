import { useState } from 'react';
import { dateLabel } from '../data/responseAdapters.js';
import { navigateToNotificationNews } from './notificationNavigation.js';
import s from './Personalization.module.css';

export default function NotificationPanel({ notifications, interests, onClose, onProfile }) {
  const [tab, setTab] = useState('list');
  const [feedback, setFeedback] = useState('');
  const [opening, setOpening] = useState(null);
  const { store, items, loading, busy, unreadCount, streamState, error } = notifications;
  const disabled = !!busy || opening !== null;
  const change = async (action, message) => {
    setFeedback('');
    if (await action()) setFeedback(message);
  };
  async function openNews(item) {
    setOpening(item.id); setFeedback('');
    try {
      if (!item.readAt && !(await store.read(item.id))) return;
      navigateToNotificationNews(item);
      onClose();
    } catch (err) { setFeedback(err.message || '관련 뉴스로 이동하지 못했습니다.'); }
    finally { setOpening(null); }
  }
  return <>
    <div className={s.notificationSummary}>
      <div><span className={s.hint}>읽지 않은 알림</span><strong>{unreadCount === null ? '—' : unreadCount.toLocaleString('ko-KR')}<small>개</small></strong></div>
      <span className={`${s.connectionState} ${streamState === 'connected' ? s.connected : ''}`} role="status"><i aria-hidden="true" />{streamState === 'connected' ? '실시간 연결됨' : streamState === 'closed' ? '실시간 연결 끊김' : '실시간 연결 중'}</span>
    </div>
    <div className={s.tabs}>
      <button type="button" aria-pressed={tab === 'list'} onClick={() => setTab('list')}>알림 목록</button>
      <button type="button" aria-pressed={tab === 'settings'} onClick={() => setTab('settings')}>수신 설정</button>
    </div>
    {error && <p className={s.error} role="alert">{error}</p>}
    {feedback && <p className={s.notificationFeedback} role="status">{feedback}</p>}
    {tab === 'settings' ? <NotificationSettings notifications={notifications} themes={interests.themes} onProfile={onProfile} change={change} /> : <>
      <div className={s.notificationToolbar}>
        <p className={s.description}>관심 테마의 새로운 소식을 모았어요.</p>
        <div>
          <button type="button" className={s.textButton} disabled={disabled || loading} onClick={() => store.refresh()}>새로고침</button>
          <button type="button" className={s.textButton} disabled={disabled || loading || !unreadCount} onClick={() => change(() => store.readAll(), '모든 알림을 확인했습니다.')}>전체 확인</button>
        </div>
      </div>
      {streamState !== 'connected' && <p className={s.hint}>연결을 복구하고 있습니다. 새로고침으로 최신 알림을 확인할 수 있어요.</p>}
      <div aria-busy={loading}>
        {loading && <p className={s.hint} role="status">알림을 불러오는 중…</p>}
        {!loading && !error && !items.length && <div className={s.empty}><h3>아직 도착한 알림이 없어요</h3><p className={s.description}>관심 테마에 새 기사가 모이면 알려드릴게요.</p><button type="button" className={s.secondary} onClick={onProfile}>관심 테마 관리</button></div>}
        <ul className={s.notificationList}>
          {items.map((item) => <li key={item.id} className={`${s.notificationItem} ${!item.readAt ? s.unreadItem : ''}`}>
            <div className={s.notificationMeta}><span>{item.fieldName} / {item.themeName}</span><span className={s.readState}>{item.readAt ? '읽음' : '안 읽음'}</span></div>
            <button type="button" className={s.notificationTitle} disabled={disabled} onClick={() => openNews(item)}>{opening === item.id ? '관련 뉴스로 이동 중…' : item.title}<span aria-hidden="true">↗</span></button>
            <p className={s.notificationMessage}>{item.message}</p>
            <div className={s.notificationFooter}>
              <span><time dateTime={item.createdAt}>{dateLabel(item.createdAt)}</time><span>기사 {item.articleCount}건</span></span>
              <div>
                {!item.readAt && <button type="button" disabled={disabled} onClick={() => change(() => store.read(item.id), '알림을 확인했습니다.')} aria-label={`${item.title} 확인`}>확인</button>}
                <button type="button" disabled={disabled} onClick={() => change(() => store.remove(item.id), '알림을 삭제했습니다.')} aria-label={`${item.title} 삭제`}>삭제</button>
              </div>
            </div>
          </li>)}
        </ul>
        {notifications.hasNext && <button type="button" className={`${s.secondary} ${s.notificationMore}`} disabled={loading || disabled} onClick={() => store.more()}>이전 알림 더 보기</button>}
      </div>
    </>}
  </>;
}

function NotificationSettings({ notifications, themes, onProfile, change }) {
  const { enabled, busy, loading, settingsError, store } = notifications;
  return <>
    <div className={s.settingRow}>
      <div><h3>전체 알림</h3><p className={s.hint}>관심 테마는 그대로 두고 모든 새 알림 수신을 한 번에 켜거나 꺼요.</p></div>
      <button type="button" role="switch" aria-checked={enabled === true} aria-label="전체 알림 수신" disabled={enabled === null || !!busy || loading} className={s.notificationSwitch} onClick={() => change(() => store.updateSettings(!enabled), enabled ? '전체 알림을 껐습니다.' : '전체 알림을 켰습니다.')}><span aria-hidden="true" />{enabled === null ? '확인 중' : enabled ? 'ON' : 'OFF'}</button>
    </div>
    {settingsError && <p className={s.error} role="alert">{settingsError} <button type="button" disabled={!!busy || loading} onClick={() => store.refresh()}>다시 시도</button></p>}
    {enabled === false && <p className={s.notificationFeedback}>전체 알림이 꺼져 있어요. 관심 테마는 유지되지만 다시 켜기 전까지 새 알림이 생성되지 않아요.</p>}
    <section className={s.section}>
      <div className={s.notificationToolbar}><h3>관심 테마 알림</h3><button type="button" className={s.textButton} onClick={onProfile}>테마 선택하기 →</button></div>
      <p className={s.description}>관심 테마로 등록하면 해당 테마의 새 기사 알림을 자동으로 받아요.</p>
      {!themes.length && <div className={s.empty}><h3>먼저 관심 테마를 선택해 주세요</h3><p>68개 테마 중 원하는 테마를 고르면 새 기사 알림을 받을 수 있어요.</p><button type="button" className={s.secondary} onClick={onProfile}>관심 테마 선택</button></div>}
      {themes.length > 0 && <div className={s.notificationThemeList} aria-label="알림 받는 관심 테마">
        {themes.map((theme) => <span key={theme.id}><i aria-hidden="true">✓</i>{theme.name}</span>)}
      </div>}
      {themes.length > 0 && <p className={s.footnote}>테마 알림을 그만 받으려면 관심 테마에서 해제해 주세요.</p>}
    </section>
  </>;
}
