# Quick test for PSEye provider
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from workers.cameraProvider_pseyepy import PSEyeProvider
import time

if __name__ == '__main__':
    print('Starting PSEyeProvider test')
    p = PSEyeProvider(0, 320, 240, 60, logQueue=None)
    print('provider:', p is not None, 'camera:', getattr(p, 'camera', None) is not None)
    for i in range(10):
        f, ts = p.read()
        print(f'iter {i}: frame is None? {f is None}, ts={ts}')
        time.sleep(0.2)
    p.close()
    print('Done')
