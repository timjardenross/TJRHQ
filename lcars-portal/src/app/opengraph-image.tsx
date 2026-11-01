import { ImageResponse } from 'next/og';
import { OG_LOCKUP_DATA_URI, OG_LOCKUP_HEIGHT, OG_LOCKUP_WIDTH } from './ogLockup';

// TJR HQ share image (brand Stage 3): the primary lockup (outlined, so no font
// loading is needed at the edge) on the family mist surface. Plain identity
// card; the earlier marketing copy belonged to the public Mind & Body site.
export const alt = 'TJR HQ, Intelligence & Operations Centre';
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = 'image/png';
export const runtime = 'edge';

const LOCKUP_W = 920;

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          display: 'flex',
          width: '100%',
          height: '100%',
          background: '#F5F7FA',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={OG_LOCKUP_DATA_URI}
          alt="TJR HQ"
          width={LOCKUP_W}
          height={Math.round((LOCKUP_W * OG_LOCKUP_HEIGHT) / OG_LOCKUP_WIDTH)}
        />
      </div>
    ),
    size
  );
}
