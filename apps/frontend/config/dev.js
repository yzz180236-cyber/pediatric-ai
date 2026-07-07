const { loadFrontendEnv } = require('./loadEnv')

loadFrontendEnv()

module.exports = {
  env: {
    NODE_ENV: '"development"',
    TARO_APP_BFF_URL: JSON.stringify(process.env.TARO_APP_BFF_URL || 'http://127.0.0.1:3000/api/v1'),
    TARO_APP_AI_ENGINE_URL: JSON.stringify(process.env.TARO_APP_AI_ENGINE_URL || 'http://127.0.0.1:8000')
  },
  defineConstants: {
  },
  mini: {},
  h5: {
    devServer: {
      host: '0.0.0.0'
    }
  }
}
