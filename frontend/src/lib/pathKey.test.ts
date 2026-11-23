import { pathKey } from './pathKey';

describe('pathKey', () => {
  it('treats slash styles, case and repeated separators as the same path', () => {
    expect(pathKey('C:\\Library\\Media\\Cover.PNG')).toBe(pathKey('c:/library//media/cover.png'));
  });

  it('ignores a trailing separator', () => {
    expect(pathKey('C:/library/media/')).toBe(pathKey('C:/library/media'));
  });

  it('folds dot and dot-dot segments', () => {
    expect(pathKey('C:/library/media/../media/./a.png')).toBe(pathKey('C:/library/media/a.png'));
  });

  it('keeps different files apart', () => {
    expect(pathKey('C:/library/a.png')).not.toBe(pathKey('C:/library/b.png'));
  });
});
