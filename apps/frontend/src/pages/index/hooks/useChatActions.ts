import { useState, useRef } from "react";
import Taro from "@tarojs/taro";
import { Message } from "@pediatric-ai/shared-types";
import { useChatStore } from "../../../store/chatStore";
import { useUserStore } from "../../../store/userStore";
import { BASE_URL, request } from "../../../utils/request";
import { ensureAuthenticated, isH5Dev } from "../../../utils/auth";
import { containsHighRiskWords } from "../../../utils/security";
import { trackEvent } from "../../../utils/tracker";

export function useChatActions() {
  const OCR_CARD_OFFSET = 500;
  const ASSESSMENT_CARD_OFFSET = 1000;
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [imageUrl, setImageUrl] = useState("");
  const [imageFileId, setImageFileId] = useState("");
  const [uploadingImage, setUploadingImage] = useState(false);
  const previewObjectUrlRef = useRef<string | null>(null);

  const messages = useChatStore((state) => state.messages);
  const addMessage = useChatStore((state) => state.addMessage);
  const clearMessages = useChatStore((state) => state.clearMessages);
  const updateMessage = useChatStore((state) => state.updateMessage);

  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const setCurrentSessionId = useChatStore(
    (state) => state.setCurrentSessionId,
  );
  const setSessions = useChatStore((state) => state.setSessions);

  const abortControllerRef = useRef<AbortController | null>(null);
  const requestTaskRef = useRef<any>(null);

  const handleStop = () => {
    if (process.env.TARO_ENV === "h5") {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    } else {
      if (requestTaskRef.current) {
        requestTaskRef.current.abort();
        requestTaskRef.current = null;
      }
    }
    setLoading(false);
  };

  const clearPreviewUrl = () => {
    if (previewObjectUrlRef.current && previewObjectUrlRef.current.startsWith("blob:")) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
    }
    previewObjectUrlRef.current = null;
  };

  const fileToDataUrl = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("read file failed"));
      reader.readAsDataURL(file);
    });

  const blobUrlToDataUrl = async (blobUrl: string): Promise<string> => {
    const response = await fetch(blobUrl);
    const blob = await response.blob();
    return fileToDataUrl(new File([blob], "clipboard-image", { type: blob.type || "image/png" }));
  };

  const upsertOcrCardMessage = (baseMsgId: number, payload: any) => {
    const cardId = baseMsgId + OCR_CARD_OFFSET;
    const existing = useChatStore.getState().messages.find((msg) => msg.id === cardId);
    if (existing) {
      updateMessage(cardId, (msg) => ({
        ...msg,
        type: "ocr_result",
        payload,
      }));
      return;
    }
    addMessage({
      id: cardId,
      text: "",
      sender: "ai",
      type: "ocr_result",
      payload,
    });
  };

  const mapMessages = (msgs: any[]): Message[] => {
    const mappedMsgs: Message[] = msgs.map((m: any) => ({
      id: m.id,
      text: m.content,
      sender: m.role,
      imageUrl: m.imageUrl,
      thoughts: m.thoughts,
      citations: m.citations,
      type: m.assessment ? "assessment_card" : undefined,
      payload: m.assessment,
      duration: m.duration ? parseFloat(m.duration) : undefined,
    }));

    if (mappedMsgs.length === 0) {
      mappedMsgs.push({
        id: 1,
        text: '你好，我是智慧儿科 AI 助手，请问宝宝今天有什么不适？',
        sender: 'ai',
      });
    }

    return mappedMsgs;
  };

  const loadSessions = async () => {
    try {
      if (isH5Dev && !useUserStore.getState().token) {
        return;
      }
      await ensureAuthenticated();
      const data = await request<any[]>("/chat/sessions", {
        method: "GET",
      });
      setSessions(data);
      if (data.length > 0 && !useChatStore.getState().currentSessionId) {
        loadSessionMessages(data[0].id);
      }
    } catch (e) {
      console.error("加载历史会话失败", e);
    }
  };

  const loadSessionMessages = async (sessionId: string) => {
    try {
      await ensureAuthenticated();
      const msgs = await request<any[]>(`/chat/sessions/${sessionId}/messages`, {
        method: "GET",
      });
      useChatStore.getState().setMessages(mapMessages(msgs));
      setCurrentSessionId(sessionId);
      
      // 检测该历史会话最新的评估是否存在重症就医标识
      const hasEmergency = msgs.some(m => m.payload?.triageLevel === 'emergency_now' || m.assessment?.triageLevel === 'emergency_now');
      useChatStore.getState().setEmergencyNow(hasEmergency);
    } catch (e) {
      console.error("加载会话记录失败", e);
    }
  };

  const createSession = async () => {
    try {
      await ensureAuthenticated();
      const data = await request<any>("/chat/sessions", {
        method: "POST",
      });
      setCurrentSessionId(data.id);
      trackEvent('chat_session_created', { sessionId: data.id });
      useChatStore.getState().setMessages([
        {
          id: 1,
          text: "你好，我是智慧儿科 AI 助手，请问宝宝今天有什么不适？",
          sender: "ai",
        },
      ]);
      const sessions = await request<any[]>("/chat/sessions", {
        method: "GET",
      });
      setSessions(sessions);
      return data.id;
    } catch (e) {
      console.error("新建会话失败", e);
    }
    return null;
  };

  const deleteSession = async (sessionId: string) => {
    try {
      Taro.showLoading({ title: '删除中...' });
      await ensureAuthenticated();
      await request<void>(`/chat/sessions/${sessionId}`, {
        method: 'DELETE',
      });
      Taro.hideLoading();
      Taro.showToast({ title: '删除成功', icon: 'success' });
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null);
        clearMessages();
      }
      trackEvent('chat_session_deleted', { sessionId });
      loadSessions();
    } catch (e) {
      Taro.hideLoading();
      console.error('删除会话失败', e);
      Taro.showToast({ title: '删除失败', icon: 'error' });
    }
  };

  const handleSend = async () => {
    const startTime = Date.now();
    const text = inputValue.trim();
    if ((!text && !imageUrl) || loading) return;

    // 本地高危拦截 (第一道防线)
    if (containsHighRiskWords(text)) {
      const userMsg: Message = { id: Date.now(), text, sender: "user", imageUrl };
      addMessage(userMsg);
      const aiMsgId = Date.now() + 1;
      addMessage({
        id: aiMsgId,
        text: '',
        sender: "ai",
        isError: true,
        thoughts: ['系统安全拦截：发现高危违规词汇，请求已被本地防线阻断。']
      });
      setInputValue('');
      setImageUrl('');
      return;
    }

    let sessionId = currentSessionId;
    if (!sessionId) {
      sessionId = await createSession();
      if (!sessionId) {
        Taro.showToast({ title: "创建会话失败，请重试", icon: "none" });
        return;
      }
    }

    const history = messages
      .filter((m) => !m.isError && m.text && m.id !== 1) // 排除欢迎语
      .slice(-10)
      .map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: m.text,
        image: null,
      }));

    const userMsg: Message = { id: Date.now(), text, sender: "user", imageUrl };
    addMessage(userMsg);
    
    const aiMsgId = Date.now() + 1;
    addMessage({ id: aiMsgId, text: '', sender: "ai", isError: false });
    
    setLoading(true);

    const snapshotText = text;
    const snapshotImage = imageUrl;
    const snapshotImageFileId = imageFileId;
    trackEvent('chat_message_sent', {
      hasImage: Boolean(snapshotImage),
      length: text.length,
    });
    setImageUrl("");
    setImageFileId("");
    setInputValue("");

    const token = await ensureAuthenticated();
    const header = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    };

    try {
      if (process.env.TARO_ENV === "h5") {
        const controller = new AbortController();
        abortControllerRef.current = controller;
        const res = await fetch(`${BASE_URL}/chat/stream`, {
          method: "POST",
          headers: header,
          body: JSON.stringify({
            sessionId,
            message: text,
            image: snapshotImageFileId ? null : snapshotImage,
            imageFileId: snapshotImageFileId,
            history,
          }),
          signal: controller.signal,
        });

        if (!res.ok) {
          if (res.status === 401) {
            useUserStore.getState().clearToken();
            Taro.showToast({
              title: isH5Dev ? "请重新登录开发账号" : "登录已过期，请重新登录",
              icon: "none",
            });
          }
          throw new Error(`HTTP ${res.status} ${res.statusText}`);
        }
        if (!res.body) throw new Error("流式响应不可用");

        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";

          for (const part of parts) {
            const lines = part.split("\n");
            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const dataStr = line.slice(6);
                if (dataStr === "[DONE]") {
                  setLoading(false);
                  return; // 遇到 DONE 彻底终结当前读取流，因为后面也不会有有效数据了。
                }
                try {
                  const data = JSON.parse(dataStr);
                  if (data.chunk) {
                    setInputValue("");
                    updateMessage(aiMsgId, (msg) => ({
                      ...msg,
                      text: msg.text + data.chunk,
                    }));
                  }
                  if (data.citations) {
                    trackEvent("chat_citations_rendered", {
                      sessionId,
                      citationCount: data.citations.length,
                      hasGuideline: data.citations.some((item: any) => item?.sourceType === "guideline"),
                    });
                    updateMessage(aiMsgId, (msg) => ({
                      ...msg,
                      citations: data.citations,
                    }));
                  }
                  if (data.ocr_result) {
                    upsertOcrCardMessage(aiMsgId, data.ocr_result);
                  }
                  if (data.assessment) {
                    trackEvent("chat_assessment_rendered", {
                      sessionId,
                      triageLevel: data.assessment.triageLevel,
                      trendDirection: data.assessment.trendDirection || "unknown",
                      hasSummary: Boolean(data.assessment.summaryText),
                      evidenceLayerCount: data.assessment.evidenceLayers?.length || 0,
                    });
                    
                    // 触碰紧急重症，切断后续非就医交互，触发全局熔断
                    if (data.assessment.triageLevel === 'emergency_now') {
                      useChatStore.getState().setEmergencyNow(true);
                    }

                    if (useChatStore.getState().messages.find((msg) => msg.id === aiMsgId + OCR_CARD_OFFSET)) {
                      addMessage({
                        id: aiMsgId + ASSESSMENT_CARD_OFFSET,
                        text: '',
                        sender: 'ai',
                        type: 'assessment_card',
                        payload: data.assessment,
                      });
                    } else {
                      updateMessage(aiMsgId, (msg) => ({
                        ...msg,
                        type: 'assessment_card',
                        payload: data.assessment,
                      }));
                    }
                  }
                  if (data.followup_card) {
                    trackEvent("chat_followup_card_rendered", {
                      sessionId,
                      optionCount: data.followup_card.options?.length || 0,
                    });
                    // 将追问卡片作为独立的 AI 消息追加，触发 FollowupCard 渲染
                    updateMessage(aiMsgId, (msg) => ({
                      ...msg,
                      type: 'followup_card',
                      payload: data.followup_card,
                    }));
                  }
                  if (data.thought) {
                    updateMessage(aiMsgId, (msg) => {
                      const thoughts = msg.thoughts || [];
                      // 防止重复追加相同的思考步骤
                      if (!thoughts.includes(data.thought)) {
                        return {
                          ...msg,
                          thoughts: [...thoughts, data.thought],
                        };
                      }
                      return msg;
                    });
                  }
                } catch (e) {}
              }
            }
          }
        }
      } else {
        const task = Taro.request({
          url: `${BASE_URL}/chat/stream`,
          method: "POST",
          header,
          data: {
            sessionId,
            message: text,
            image: snapshotImageFileId ? null : snapshotImage,
            imageFileId: snapshotImageFileId,
            history,
          },
          enableChunked: true,
          success: (res: any) => {
            if (res.statusCode === 401) {
              useUserStore.getState().clearToken();
              Taro.showToast({
                title: isH5Dev ? "请重新登录开发账号" : "登录已过期，请重新登录",
                icon: "none",
              });
            }
            if (res.statusCode < 200 || res.statusCode >= 300) {
              updateMessage(aiMsgId, (msg) => ({
                ...msg,
                text:
                  msg.text + `\n[网络错误] 请求失败: HTTP ${res.statusCode}`,
                isError: true,
              }));
            }
          },
          fail: (err: any) => {
            updateMessage(aiMsgId, (msg) => ({
              ...msg,
              text:
                msg.text +
                `\n[网络错误] 流式请求失败: ${err.errMsg || "未知错误"}`,
              isError: true,
            }));
          },
        });
        requestTaskRef.current = task;

        let buffer = "";
        task.onChunkReceived((res: any) => {
          const decoder = new TextDecoder("utf-8");
          buffer += decoder.decode(new Uint8Array(res.data));
          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";

          for (const part of parts) {
            const lines = part.split("\n");
            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const dataStr = line.slice(6);
                if (dataStr === "[DONE]") continue;
                try {
                  const data = JSON.parse(dataStr);
                  if (data.chunk) {
                    setInputValue("");
                    updateMessage(aiMsgId, (msg) => ({
                      ...msg,
                      text: msg.text + data.chunk,
                    }));
                  }
                  if (data.citations) {
                    trackEvent("chat_citations_rendered", {
                      sessionId,
                      citationCount: data.citations.length,
                      hasGuideline: data.citations.some((item: any) => item?.sourceType === "guideline"),
                    });
                    updateMessage(aiMsgId, (msg) => ({
                      ...msg,
                      citations: data.citations,
                    }));
                  }
                  if (data.ocr_result) {
                    upsertOcrCardMessage(aiMsgId, data.ocr_result);
                  }
                  if (data.assessment) {
                    trackEvent("chat_assessment_rendered", {
                      sessionId,
                      triageLevel: data.assessment.triageLevel,
                      trendDirection: data.assessment.trendDirection || "unknown",
                      hasSummary: Boolean(data.assessment.summaryText),
                      evidenceLayerCount: data.assessment.evidenceLayers?.length || 0,
                    });
                    
                    // 触碰紧急重症，切断后续非就医交互，触发全局熔断
                    if (data.assessment.triageLevel === 'emergency_now') {
                      useChatStore.getState().setEmergencyNow(true);
                    }

                    if (useChatStore.getState().messages.find((msg) => msg.id === aiMsgId + OCR_CARD_OFFSET)) {
                      addMessage({
                        id: aiMsgId + ASSESSMENT_CARD_OFFSET,
                        text: '',
                        sender: 'ai',
                        type: 'assessment_card',
                        payload: data.assessment,
                      });
                    } else {
                      updateMessage(aiMsgId, (msg) => ({
                        ...msg,
                        type: 'assessment_card',
                        payload: data.assessment,
                      }));
                    }
                  }
                  if (data.thought) {
                    updateMessage(aiMsgId, (msg) => {
                      const thoughts = msg.thoughts || [];
                      // 防止重复追加相同的思考步骤
                      if (!thoughts.includes(data.thought)) {
                        return {
                          ...msg,
                          thoughts: [...thoughts, data.thought],
                        };
                      }
                      return msg;
                    });
                  }
                } catch (e) {}
              }
            }
          }
        });
      }
    } catch (e: any) {
      setInputValue(snapshotText);
      setImageUrl(snapshotImage);

      if (e.name === "AbortError" || e.errMsg?.includes("abort")) {
        console.log("用户主动中断了请求");
        trackEvent("chat_stream_aborted", {
          sessionId,
          hasImage: Boolean(snapshotImage),
          inputLength: snapshotText.length,
        });
        updateMessage(aiMsgId, (msg) => ({
          ...msg,
          text: msg.text ? msg.text + "\n\n[已中止回答]" : "[已中止回答]",
          isError: true,
        }));
      } else {
        updateMessage(aiMsgId, (msg) => ({
          ...msg,
          text: msg.text + `\n[网络错误] 流式请求中断: ${e.message}`,
          isError: true,
        }));
      }
    } finally {
      const duration = (Date.now() - startTime) / 1000;
      updateMessage(aiMsgId, (msg) => ({ ...msg, duration }));
      setLoading(false);
      abortControllerRef.current = null;
      requestTaskRef.current = null;
    }
  };

  const handleClearChat = () => {
    Taro.showModal({
      title: "清空会话",
      content: "确定要清空当前的聊天记录吗？",
      success: (res: any) => {
        if (res.confirm) {
          clearMessages();
        }
      },
    });
  };

  const handleRichCardAction = async (action: string, payload?: unknown) => {
    if (!currentSessionId) {
      Taro.showToast({ title: "当前会话不存在", icon: "none" });
      return;
    }

    if (action === "followup_option_selected") {
      const optionText = String((payload as any)?.option || "").trim();
      if (!optionText) {
        return;
      }
      trackEvent("chat_followup_option_selected", {
        sessionId: currentSessionId,
        option: optionText,
      });
      setInputValue(optionText);
      return;
    }

    if (action !== "mark_followup" && action !== "request_doctor_review") {
      return;
    }

    try {
      await ensureAuthenticated();
      await request(`/chat/sessions/${currentSessionId}/actions`, {
        method: "POST",
        data: { action },
      });
      await loadSessions();
      trackEvent("chat_result_action_completed", {
        sessionId: currentSessionId,
        action,
      });
      Taro.showToast({
        title: action === "mark_followup" ? "已标记待随访" : "已提交医生复核",
        icon: "success",
      });
    } catch (error) {
      console.error("执行问诊结果动作失败", error);
      Taro.showToast({ title: "操作失败", icon: "none" });
    }
  };

  const doUpload = async (fileOrPath: File | string) => {
    setUploadingImage(true);
    try {
      const localPreviewUrl =
        fileOrPath instanceof File
          ? await fileToDataUrl(fileOrPath)
          : (process.env.TARO_ENV === "h5" && String(fileOrPath).startsWith("blob:"))
            ? await blobUrlToDataUrl(String(fileOrPath))
            : fileOrPath;
      clearPreviewUrl();
      previewObjectUrlRef.current = localPreviewUrl.startsWith("blob:") ? localPreviewUrl : null;
      setImageUrl(localPreviewUrl);

      if (process.env.TARO_ENV === "h5" && fileOrPath instanceof File) {
        const token = await ensureAuthenticated();
        const formData = new FormData();
        formData.append("file", fileOrPath);
        const res = await fetch(`${BASE_URL}/chat/files`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        });
        if (!res.ok) throw new Error("上传失败");
        const data = await res.json() as { url: string; fileId: string };
        setImageFileId(data.fileId);
      } else {
        const path = localPreviewUrl;
        const token = await ensureAuthenticated();
        const res = await new Promise<any>((resolve, reject) => {
          Taro.uploadFile({
            url: `${BASE_URL}/chat/files`,
            filePath: path,
            name: "file",
            header: {
              Authorization: `Bearer ${token}`,
            },
            success: resolve,
            fail: reject,
          });
        });
        if (res.statusCode >= 400) throw new Error("上传失败");
        const data = JSON.parse(res.data);
        setImageFileId(data.fileId);
      }
    } catch (e) {
      clearPreviewUrl();
      setImageUrl("");
      setImageFileId("");
      console.error("上传图片失败", e);
      Taro.showToast({
        title: "图片上传失败，请重试",
        icon: "error",
      });
    } finally {
      setUploadingImage(false);
    }
  };

  const handleUploadImage = () => {
    Taro.chooseImage({
      count: 1,
      sizeType: ["compressed"],
      sourceType: ["album", "camera"],
      success: (res: any) => {
        const file =
          process.env.TARO_ENV === "h5"
            ? res.tempFiles?.[0]?.originalFile
            : null;
        doUpload(file || res.tempFilePaths[0]);
      },
      fail: (err: any) => {
        console.error("选择图片取消或失败:", err);
      },
    });
  };

  return {
    inputValue,
    setInputValue,
    loading,
    imageUrl,
    setImageUrl,
    setImageFileId,
    uploadingImage,
    messages,
    clearPreviewUrl,
    handleSend,
    handleStop,
    handleClearChat,
    doUpload,
    handleUploadImage,
    handleRichCardAction,
    loadSessions,
    loadSessionMessages,
    createSession,
    deleteSession,
  };
}
