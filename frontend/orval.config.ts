import { defineConfig } from 'orval'

export default defineConfig({
  peach1upApi: {
    input: {
      target: 'http://localhost:8000/api/openapi.json',
    },
    output: {
      mode: 'tags-split',
      target: 'src/api/generated/index.ts',
      schemas: 'src/api/generated/schemas',
      client: 'react-query',
      clean: true,
    },
  },
})
