import { useEffect, useState } from 'react';
import { APIService } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { initials } from './presentation';

export function PlayerAvatar({ member, className = 'ch-avatar' }) {
  const { token } = useAuth();
  const photo = member?.photo;
  const [loaded, setLoaded] = useState(null);
  useEffect(() => {
    if (photo?.source !== 'club') return;
    const controller = new AbortController();
    let url;
    APIService.clubPlayerPhotoBlob(photo.url, controller.signal).then(blob => {
      if (controller.signal.aborted) return;
      url = URL.createObjectURL(blob);
      setLoaded({ key: `${photo.url}:${photo.updated_at}:${token}`, url });
    }).catch(() => {});
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [photo?.source, photo?.url, photo?.updated_at, token]);
  const src = photo?.source === 'club'
    ? (loaded?.key === `${photo.url}:${photo.updated_at}:${token}` ? loaded.url : null)
    : photo?.url;
  return <span className={className}>{src ? <img src={src} alt="" /> : initials(member?.display_name)}</span>;
}
