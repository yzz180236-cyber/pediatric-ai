import React, { useState, useEffect } from "react";
import Taro from "@tarojs/taro";
import { View, ScrollView } from "@tarojs/components";
import { Input, Button } from "@nutui/nutui-react-taro";
import { ChatBubble } from "../../components/ChatBubble";
import { ChatInputBar } from "../../components/ChatInputBar";
import { useChatActions } from "./hooks/useChatActions";
import { useChatStore } from "../../store/chatStore";
import { useUserStore } from "../../store/userStore";
import { devLogin, isH5Dev } from "../../utils/auth";
import "./index.scss";

export default function Index() {
  const [activeTab, setActiveTab] = useState<"chat" | "profile">("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [devUsername, setDevUsername] = useState("boluo123");
  const [devPassword, setDevPassword] = useState("admin123");
  const [devLoginLoading, setDevLoginLoading] = useState(false);

  const {
    inputValue,
    setInputValue,
    loading,
    imageUrl,
    setImageUrl,
    uploadingImage,
    messages,
    handleSend,
    handleStop,
    handleClearChat,
    doUpload,
    handleUploadImage,
    loadSessions,
    loadSessionMessages,
    createSession,
    deleteSession,
  } = useChatActions();

  const sessions = useChatStore((state) => state.sessions);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const token = useUserStore((state) => state.token);
  const role = useUserStore((state) => state.role);
  const showDevLogin = isH5Dev && !token;

  useEffect(() => {
    if (showDevLogin) {
      return;
    }
    loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showDevLogin]);

  const handleDevLogin = async () => {
    if (!devUsername.trim() || !devPassword.trim()) {
      Taro.showToast({ title: "请输入账号密码", icon: "none" });
      return;
    }

    setDevLoginLoading(true);
    try {
      await devLogin(devUsername.trim(), devPassword.trim());
      await loadSessions();
      Taro.showToast({ title: "登录成功", icon: "success" });
    } catch (error: any) {
      Taro.showToast({ title: error?.message || "登录失败", icon: "none" });
    } finally {
      setDevLoginLoading(false);
    }
  };

  return (
    <View className="app-container">
      <View
        className="app-header"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <View
          onClick={() => setDrawerOpen(true)}
          style={{
            padding: "0 10px",
            fontSize: "24px",
            cursor: "pointer",
            lineHeight: "1",
          }}
        >
          ≡
        </View>
        <View>智慧儿科</View>
        <View style={{ width: "44px" }}></View>
      </View>

      {drawerOpen && (
        <View className="drawer-overlay" onClick={() => setDrawerOpen(false)}>
          <View className="drawer-content" onClick={(e) => e.stopPropagation()}>
            <View className="drawer-header">
              <View>历史问诊记录</View>
              <View
                onClick={async () => {
                  await createSession();
                  setDrawerOpen(false);
                }}
                style={{
                  color: "#764ba2",
                  cursor: "pointer",
                  fontSize: "14px",
                  fontWeight: "normal",
                }}
              >
                + 新建
              </View>
            </View>
            {role === 'doctor' && (
              <View
                className="session-item drawer-entry-card"
                onClick={() => {
                  Taro.navigateTo({ url: '/pages/doctor/workbench/index' })
                  setDrawerOpen(false)
                }}
              >
                <View className="session-title">医生工作台</View>
                <View className="session-time">查看预诊单、随访与患儿会话</View>
              </View>
            )}
            <ScrollView scrollY className="drawer-list">
              {sessions.map((s) => (
                <View
                  key={s.id}
                  className={`session-item ${currentSessionId === s.id ? "active" : ""}`}
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  onClick={() => {
                    loadSessionMessages(s.id);
                    setDrawerOpen(false);
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <View className="session-title">会话 {s.id.slice(0, 8)}</View>
                    <View className="session-time">
                      {new Date(s.lastActiveAt).toLocaleString()}
                    </View>
                  </View>
                  <View 
                    onClick={(e) => {
                      e.stopPropagation();
                      Taro.showModal({
                        title: '删除会话',
                        content: '确定要删除这条问诊记录吗？',
                        success: (res) => {
                          if (res.confirm) {
                            deleteSession(s.id);
                          }
                        }
                      });
                    }}
                    style={{ padding: '4px 8px', color: '#ff4d4f', fontSize: '14px', cursor: 'pointer' }}
                  >
                    🗑️
                  </View>
                </View>
              ))}
              {sessions.length === 0 && (
                <View
                  style={{
                    padding: "20px",
                    textAlign: "center",
                    color: "#999",
                    fontSize: "14px",
                  }}
                >
                  暂无历史记录
                </View>
              )}
            </ScrollView>
          </View>
        </View>
      )}

      <View className="custom-tabs-header">
        <View
          className={`tab-item ${activeTab === "chat" ? "active" : ""}`}
          onClick={() => setActiveTab("chat")}
        >
          智能问诊
        </View>
        <View
          className={`tab-item ${activeTab === "profile" ? "active" : ""}`}
          onClick={() => setActiveTab("profile")}
        >
          宝宝档案
        </View>
      </View>

      <View className="app-main-content">
        {showDevLogin ? (
          <View className="tab-content-wrapper dev-login-wrapper">
            <View className="growth-record-card dev-login-card">
              <View className="card-title">开发登录</View>
              <View className="dev-login-tip">H5 开发环境使用内测账号登录</View>
              <Input
                value={devUsername}
                onChange={setDevUsername}
                placeholder="账号（家长: boluo123 / 医生: doctor001）"
                className="record-input"
              />
              <Input
                value={devPassword}
                onChange={setDevPassword}
                placeholder="密码"
                type="password"
                className="record-input dev-login-password"
              />
              <Button
                type="primary"
                block
                loading={devLoginLoading}
                disabled={devLoginLoading}
                onClick={handleDevLogin}
                className="record-save-btn submit-btn-full"
              >
                {devLoginLoading ? "登录中..." : "登录"}
              </Button>
            </View>
          </View>
        ) : activeTab === "chat" ? (
          <View className="tab-content-wrapper">
            <ScrollView
              scrollY
              scrollWithAnimation={false}
              className="app-chat-area"
              scrollIntoView={
                messages.length > 0
                  ? `anchor-${messages[messages.length - 1].id}-${JSON.stringify(messages[messages.length - 1]).length}`
                  : ""
              }
            >
              {messages.map((msg) => (
                <View key={msg.id} id={`msg-${msg.id}`}>
                  <ChatBubble msg={msg} />
                </View>
              ))}
              {messages.length > 0 && (
                <View
                  id={`anchor-${messages[messages.length - 1].id}-${JSON.stringify(messages[messages.length - 1]).length}`}
                  style={{ height: "20px" }}
                />
              )}
            </ScrollView>

            <ChatInputBar
              value={inputValue}
              imageUrl={imageUrl}
              onChange={setInputValue}
              onSend={handleSend}
              onStop={handleStop}
              loading={loading || uploadingImage}
              onClear={handleClearChat}
              onUploadImage={handleUploadImage}
              onClearImage={() => setImageUrl("")}
              onPasteFile={doUpload}
            />
          </View>
        ) : (
          <View className="profile-tab-entry">
            <View className="profile-tab-card">
              <View className="card-title">宝宝档案</View>
              <View className="profile-tab-copy">
                管理宝宝基础资料、电子排敏卡和生长记录。
              </View>
              <Button
                type="primary"
                block
                onClick={() => Taro.navigateTo({ url: '/pages/profile/index' })}
                className="record-save-btn submit-btn-full"
              >
                进入宝宝档案
              </Button>
            </View>
          </View>
        )}
      </View>
    </View>
  );
}
