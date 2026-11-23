import { Trash2 } from 'lucide-react';
import { useState } from 'react';
import { api } from '../lib/api';

/**
 * 지우기 버튼(U5, 2026-11-23): 누르면 "지울까요?"를 그 자리에 보이고, "지우기"를 한 번 더 눌러야 서버에 DELETE를 보냄.
 * 브라우저 확인 창(confirm)을 쓰지 않음. 공개 시연 주소에서는 서버가 403으로 막고 그 문장을 그대로 보임.
 */
export function DeleteButton({ path, what, onDeleted }: { path: string; what: string; onDeleted: () => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const remove = async () => {
    setBusy(true); setError(null);
    try { await api(path, { method: 'DELETE' }); setAsking(false); onDeleted(); }
    catch (e) { setError(e instanceof Error ? e.message : '지우지 못했습니다'); }
    finally { setBusy(false); }
  };
  if (!asking) return <button type="button" className="button ghost small" aria-label={`${what} 지우기`} onClick={() => setAsking(true)}><Trash2 size={14} /></button>;
  return <span className="delete-confirm" role="group" aria-label={`${what} 지우기 확인`}>
    <small>{what}을(를) 지울까요? 되돌릴 수 없습니다.</small>
    <button type="button" className="button small danger" disabled={busy} onClick={() => void remove()}>지우기</button>
    <button type="button" className="button ghost small" disabled={busy} onClick={() => { setAsking(false); setError(null); }}>그만두기</button>
    {error && <small role="alert" className="inline-error">{error}</small>}
  </span>;
}
