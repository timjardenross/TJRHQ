import { ImageResponse } from 'next/og';

export const alt = 'TJR Mind & Body social sharing image';
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = 'image/png';
export const runtime = 'edge';

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          display: 'flex',
          width: '100%',
          height: '100%',
          background: 'linear-gradient(135deg, #f4f7fc 0%, #dfe9fb 52%, #eaf0fb 100%)',
          color: '#172033',
          padding: 56,
          fontFamily: 'sans-serif',
          justifyContent: 'space-between',
          alignItems: 'stretch',
        }}
      >
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            width: '72%',
            borderRadius: 40,
            padding: '36px 40px',
            background: 'rgba(255,255,255,0.82)',
            boxShadow: '0 24px 80px rgba(23,32,51,0.10)',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ fontSize: 22, letterSpacing: 4, textTransform: 'uppercase', color: '#4b5c78' }}>
              TJR Mind & Body
            </div>
            <div style={{ fontSize: 66, lineHeight: 1.05, fontWeight: 700 }}>
              Practical resilience for real-life pressure
            </div>
            <div style={{ fontSize: 28, lineHeight: 1.4, color: '#44556f' }}>
              Coaching, education, and steady rebuilding for people navigating stress, pain, burnout, and disruption.
            </div>
          </div>
          <div style={{ fontSize: 26, color: '#243b7a' }}>
            tjrmindbody.com
          </div>
        </div>

        <div
          style={{
            width: '22%',
            borderRadius: 40,
            background: '#1f2f5f',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            fontSize: 30,
            lineHeight: 1.4,
            textAlign: 'center',
            padding: 24,
          }}
        >
          Support
          <br />
          Coaching
          <br />
          Education
        </div>
      </div>
    ),
    size
  );
}
