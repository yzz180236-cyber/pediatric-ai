import { Component, PropsWithChildren } from 'react'
import '@tarojs/components/dist/taro-components/taro-components.css'
import '@nutui/nutui-react-taro/dist/style.css'
import './app.scss'
import { isH5Dev, wxLogin } from './utils/auth'
import { useUserStore } from './store/userStore'

class App extends Component<PropsWithChildren> {

  async componentDidMount () {
    const token = useUserStore.getState().token;
    if (!token && !isH5Dev) {
      try {
        await wxLogin();
      } catch (err) {
        console.error('应用启动时自动登录失败:', err);
      }
    }
  }

  componentDidShow () {}

  componentDidHide () {}

  render () {
    return this.props.children
  }
}

export default App
