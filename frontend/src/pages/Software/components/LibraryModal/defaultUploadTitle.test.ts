import { defaultUploadTitle } from './defaultUploadTitle';

function makeFile(name: string, relPath?: string): File {
  const file = new File(['x'], name);
  if (relPath !== undefined) {
    Object.defineProperty(file, 'webkitRelativePath', { value: relPath });
  }
  return file;
}

describe('defaultUploadTitle', () => {
  it('uses the single media file name without extension, kept as is', () => {
    const files = [
      makeFile('Armored Core (USA).chd', 'Armored Core/Armored Core (USA).chd'),
      makeFile('cover.jpg', 'Armored Core/cover.jpg'),
    ];
    expect(defaultUploadTitle(files)).toBe('Armored Core (USA)');
  });

  it('matches extensions case-insensitively', () => {
    const files = [makeFile('Game.ISO', 'Dir/Game.ISO'), makeFile('cover.png', 'Dir/cover.png')];
    expect(defaultUploadTitle(files)).toBe('Game');
  });

  it('falls back to the folder name when several media files are selected', () => {
    const files = [
      makeFile('Disc 1.chd', 'Final Fantasy VII/Disc 1.chd'),
      makeFile('Disc 2.chd', 'Final Fantasy VII/Disc 2.chd'),
    ];
    expect(defaultUploadTitle(files)).toBe('Final Fantasy VII');
  });

  it('falls back to the folder name when no media file is recognised', () => {
    const files = [
      makeFile('readme.txt', 'Stuff/readme.txt'),
      makeFile('cover.jpg', 'Stuff/cover.jpg'),
    ];
    expect(defaultUploadTitle(files)).toBe('Stuff');
  });

  it('uses the first path segment for nested selections', () => {
    const files = [makeFile('a.txt', 'Top/Sub/a.txt'), makeFile('b.txt', 'Top/Sub/b.txt')];
    expect(defaultUploadTitle(files)).toBe('Top');
  });

  it('does not treat an extension-less or dotfile name as media', () => {
    const files = [makeFile('iso', 'Dir/iso'), makeFile('.chd', 'Dir/.chd')];
    expect(defaultUploadTitle(files)).toBe('Dir');
  });

  it('keeps only the last extension and inner dots in the stem', () => {
    const files = [makeFile('Game v1.2.iso', 'Dir/Game v1.2.iso')];
    expect(defaultUploadTitle(files)).toBe('Game v1.2');
  });

  it('returns an empty string for an empty selection', () => {
    expect(defaultUploadTitle([])).toBe('');
  });

  it('returns an empty string when no relative path is available and no media file exists', () => {
    expect(defaultUploadTitle([makeFile('notes.txt')])).toBe('');
  });
});
