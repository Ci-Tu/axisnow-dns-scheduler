import { createApp } from 'vue'
import 'flag-icons/css/flag-icons.min.css'
import './styles/base.css'
import App from './App.vue'
import { router } from './router'

createApp(App).use(router).mount('#app')
