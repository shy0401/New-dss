import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DeleteButton } from './DeleteButton';

afterEach(() => { vi.restoreAllMocks(); });

describe('DeleteButton (U5)', () => {
  it('asks in place first and sends DELETE only on the second press; a 204 with no body counts as done', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }));
    const onDeleted = vi.fn();
    render(<DeleteButton path="/scenarios/s1" what="이 계획안" onDeleted={onDeleted} />);
    fireEvent.click(screen.getByRole('button', { name: '이 계획안 지우기' }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/지울까요\? 되돌릴 수 없습니다/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '지우기' }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith('/api/scenarios/s1', expect.objectContaining({ method: 'DELETE' }));
  });

  it('can be called off without a request, and shows the server sentence when it refuses (public demo 403)', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: '공개 시연 주소에서는 지울 수 없습니다' }), { status: 403, headers: { 'Content-Type': 'application/json' } }));
    const onDeleted = vi.fn();
    render(<DeleteButton path="/reports/r1" what="이 보고서" onDeleted={onDeleted} />);
    fireEvent.click(screen.getByRole('button', { name: '이 보고서 지우기' }));
    fireEvent.click(screen.getByRole('button', { name: '그만두기' }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '이 보고서 지우기' }));
    fireEvent.click(screen.getByRole('button', { name: '지우기' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', '공개 시연 주소에서는 지울 수 없습니다');
    expect(onDeleted).not.toHaveBeenCalled();
  });
});
