const { loadFrontendEnv } = require('./loadEnv')

loadFrontendEnv()

module.exports = {
  env: {
    NODE_ENV: '"production"',
    TARO_APP_BFF_URL: JSON.stringify(process.env.TARO_APP_BFF_URL || 'https://api.pediatric.example.com/api/v1'),
    TARO_APP_AI_ENGINE_URL: JSON.stringify(process.env.TARO_APP_AI_ENGINE_URL || 'https://ai.pediatric.example.com')
  },
  defineConstants: {
  },
  mini: {},
  h5: {}
}
