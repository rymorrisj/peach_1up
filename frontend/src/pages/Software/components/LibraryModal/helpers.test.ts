import { folderNameFor, stageFolderFiles } from './helpers'

function makeFile(name: string, webkitRelativePath?: string): File {
  const file = new File(['x'], name)
  if (webkitRelativePath !== undefined) {
    Object.defineProperty(file, 'webkitRelativePath', { value: webkitRelativePath })
  }
  return file
}

// Array.from() accepts an array-like (length + numeric indices), so a real
// iterator isn't needed here, just enough shape for stageFolderFiles' own
// Array.from(fileList) call to see every file in order.
function makeFileList(files: File[]): FileList {
  const fileList: Record<number, File> = {}
  files.forEach((f, i) => { fileList[i] = f })
  return { ...fileList, length: files.length, item: (i: number) => files[i] ?? null } as unknown as FileList
}

describe('folderNameFor', () => {
  it('returns the immediate containing folder from webkitRelativePath', () => {
    const file = makeFile('track.bin', 'Disc 1/track.bin')
    expect(folderNameFor(file)).toBe('Disc 1')
  })

  it('uses the deepest folder segment for a nested relative path', () => {
    const file = makeFile('track.bin', 'Game/Disc 2/track.bin')
    expect(folderNameFor(file)).toBe('Disc 2')
  })

  it('falls back to the file stem when no relative path is present', () => {
    const file = makeFile('game.iso')
    expect(folderNameFor(file)).toBe('game')
  })
})

describe('stageFolderFiles', () => {
  it('renames a single file per folder+extension group to "{folder}{ext}"', () => {
    const files = [makeFile('a.bin', 'Disc 1/a.bin'), makeFile('b.bin', 'Disc 2/b.bin')]
    const staged = stageFolderFiles(makeFileList(files))
    expect(staged.map((s) => s.file.name)).toEqual(['Disc 1.bin', 'Disc 2.bin'])
  })

  it('numbers colliding filenames within the same folder+extension group as "{folder}_{n}{ext}"', () => {
    const files = [
      makeFile('track01.bin', 'Disc 1/track01.bin'),
      makeFile('track02.bin', 'Disc 1/track02.bin'),
    ]
    const staged = stageFolderFiles(makeFileList(files))
    expect(staged.map((s) => s.file.name)).toEqual(['Disc 1_1.bin', 'Disc 1_2.bin'])
  })

  it('preserves source order across mixed folders', () => {
    const files = [
      makeFile('a.bin', 'Disc 1/a.bin'),
      makeFile('b.bin', 'Disc 2/b.bin'),
      makeFile('c.bin', 'Disc 1/c.bin'),
    ]
    const staged = stageFolderFiles(makeFileList(files))
    expect(staged.map((s) => s.file.name)).toEqual(['Disc 1_1.bin', 'Disc 2.bin', 'Disc 1_2.bin'])
  })

  it('assigns each staged disc a unique id', () => {
    const files = [makeFile('a.bin', 'Disc 1/a.bin'), makeFile('b.bin', 'Disc 2/b.bin')]
    const staged = stageFolderFiles(makeFileList(files))
    expect(new Set(staged.map((s) => s.id)).size).toBe(2)
  })
})
