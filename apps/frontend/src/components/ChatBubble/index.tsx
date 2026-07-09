import React, { useState, useEffect } from "react";
import { View, Text, Image } from "@tarojs/components";
import { DietaryFormCard } from "../RichCards/DietaryFormCard";
import { OcrResultCard } from "../RichCards/OcrResultCard";
import { FollowupCard } from "../RichCards/FollowupCard";
import { AssessmentCard } from "../RichCards/AssessmentCard";
import { Message } from "@pediatric-ai/shared-types";
import "./index.scss";
import Taro from "@tarojs/taro";

interface ChatBubbleProps {
  msg: Message;
  onAction?: (action: string, payload?: any) => void;
}

/** H5 环境下使用 marked + dangerouslySetInnerHTML 渲染 Markdown */
function MarkdownRenderer({ text }: { text: string }) {
  if (process.env.TARO_ENV === "h5") {
    // 动态 require marked，避免在小程序端报错
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { marked } = require("marked");

    // 配置 marked：让有序列表从实际数字开始，保留原始序号
    marked.setOptions({
      gfm: true,
      breaks: true,
    });

    const html = marked.parse(text) as string;

    return (
      <View
        className="md-body"
        // @ts-ignore Taro H5 支持 dangerouslySetInnerHTML
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  }

  // 非 H5 环境（小程序）降级：简单文本展示
  return <Text>{text}</Text>;
}

export function ChatBubble({ msg, onAction }: ChatBubbleProps) {
  const isUser = msg.sender === "user";
  const isLoading =
    !isUser && !msg.text && !msg.isError && !(msg.type && msg.payload);

  const [thinkTime, setThinkTime] = useState(0);
  const [showThoughts, setShowThoughts] = useState(true);

  useEffect(() => {
    let timer: any;
    if (isLoading) {
      const startTime = Date.now();
      timer = setInterval(() => {
        setThinkTime((Date.now() - startTime) / 1000);
      }, 100);
    }
    return () => clearInterval(timer);
  }, [isLoading]);

  const renderRichCard = () => {
    switch (msg.type) {
      case "dietary_form":
        return <DietaryFormCard payload={msg.payload} onAction={onAction} />;
      case "ocr_result":
        return <OcrResultCard payload={msg.payload} />;
      case "followup_card":
        return <FollowupCard payload={msg.payload} onAction={onAction} />;
      case "assessment_card":
        return <AssessmentCard payload={msg.payload} onAction={onAction} />;
      default:
        return null;
    }
  };

  const rawText = msg.text || "";
  let thinkContent = "";
  let displayContent = rawText;

  // 匹配 <think>...</think>，包括未闭合的半截标签
  const thinkMatch = rawText.match(/<think>([\s\S]*?)(?:<\/think>|$)/i);
  if (thinkMatch) {
    thinkContent = thinkMatch[1].trim();
    // 去除 <think> 部分，剩下的作为气泡正文
    displayContent = rawText
      .replace(/<think>[\s\S]*?(?:<\/think>|$)/i, "")
      .trim();
  }

  // 合并节点汇报产生的 thoughts 与大模型流式产生的 thinkContent
  const allThoughts = [...(msg.thoughts || [])];
  if (thinkContent) {
    allThoughts.push(thinkContent);
  }
  const citationTypeLabelMap: Record<string, string> = {
    guideline: "指南引用",
    safety_rule: "安全规则",
    model_inference: "模型推断",
  };
  const aggregatedCitations = (() => {
    const sourceCitations = msg.citations || [];
    const grouped = new Map<
      string,
      { title: string; chapter?: string; sourceType?: string; count: number }
    >();

    for (const citation of sourceCitations) {
      const key = [
        citation.title || "",
        citation.chapter || "",
        citation.sourceType || "",
      ].join("::");

      const existing = grouped.get(key);
      if (existing) {
        existing.count += 1;
      } else {
        grouped.set(key, {
          title: citation.title,
          chapter: citation.chapter,
          sourceType: citation.sourceType,
          count: 1,
        });
      }
    }

    return Array.from(grouped.values());
  })();

  return (
    <View className={`chat-bubble-wrapper ${isUser ? "is-user" : "is-ai"}`}>
      <View className={`chat-bubble-content ${msg.isError ? "is-error" : ""}`}>
        <View className="text-content">
          {allThoughts.length > 0 && (
            <View
              className="thoughts-container"
              style={{
                backgroundColor: "rgba(255,255,255,0.6)",
                padding: "8px 12px",
                borderRadius: "8px",
                marginBottom: "10px",
                fontSize: "12px",
                color: "#666",
                borderLeft: "3px solid #ccc",
                boxShadow: "0 2px 8px rgba(0,0,0,0.05)",
                minWidth: "260px",
              }}
            >
              <View
                style={{
                  display: "flex",
                  alignItems: "center",
                  cursor: "pointer",
                }}
                onClick={() => setShowThoughts(!showThoughts)}
              >
                <Text style={{ fontWeight: "bold", flexShrink: 0 }}>
                  AI 思考过程
                </Text>
                {!showThoughts && (
                  <Text
                    style={{
                      marginLeft: "8px",
                      color: "#999",
                      flex: 1,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {allThoughts[allThoughts.length - 1]}
                  </Text>
                )}
                <Text
                  style={{
                    marginLeft: "auto",
                    fontSize: "10px",
                    flexShrink: 0,
                    paddingLeft: "8px",
                  }}
                >
                  {showThoughts ? "▲ 收起" : "▼ 展开"}
                </Text>
              </View>
              {showThoughts && (
                <View
                  style={{
                    marginTop: "8px",
                    borderTop: "1px solid rgba(0,0,0,0.05)",
                    paddingTop: "6px",
                  }}
                >
                  {allThoughts.map((t, i) => (
                    <View
                      key={i}
                      style={{
                        marginTop: "6px",
                        lineHeight: "1.5",
                        wordBreak: "break-word",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {/* 如果是长文本推理，就不显示勾号；如果是短状态，显示勾号 */}
                      {t.length > 30 || t.includes("\n") ? t : `✓ ${t}`}
                    </View>
                  ))}
                </View>
              )}
            </View>
          )}

          {msg.imageUrl && (
            <Image
              src={msg.imageUrl}
              mode="aspectFill"
              style={{
                width: "200px",
                height: "200px",
                borderRadius: "8px",
                marginBottom: msg.text ? "12px" : "0",
                display: "block",
                backgroundColor: "rgba(0,0,0,0.05)",
              }}
              onClick={() => {
                if (process.env.TARO_ENV === "h5") {
                  // H5 降级：直接在新标签页打开大图
                  window.open(msg.imageUrl!, "_blank");
                } else {
                  // 小程序：使用微信原生图片预览组件
                  Taro.previewImage({
                    current: msg.imageUrl!,
                    urls: [msg.imageUrl!],
                  }).catch(() => {
                    // 兼容极个别基础库版本兜底
                    Taro.showToast({ title: "无法预览", icon: "none" });
                  });
                }
              }}
            />
          )}
          {isLoading ? (
            <View
              className="loading-container"
              style={{ display: "flex", alignItems: "center" }}
            >
              <View className="loading-dots">
                <View className="dot" />
                <View className="dot" />
                <View className="dot" />
              </View>
              <Text
                className="thinking-timer"
                style={{ fontSize: "12px", color: "#999", marginLeft: "8px" }}
              >
                生成中 {thinkTime.toFixed(1)}s
              </Text>
            </View>
          ) : !isUser && displayContent && msg.type !== "ocr_result" ? (
            <MarkdownRenderer text={displayContent} />
          ) : msg.type !== "ocr_result" ? (
            <Text>{displayContent}</Text>
          ) : null}
        </View>

        {/* 化验单卡片：渲染在思考过程下方 */}
        {renderRichCard()}

        {/* 化验单卡片的 AI 分析建议：紧跟卡片后面单独渲染 */}
        {msg.type === "ocr_result" && displayContent ? (
          <View style={{ marginTop: "12px" }}>
            <MarkdownRenderer text={displayContent} />
          </View>
        ) : null}

        {aggregatedCitations.length > 0 && (
          <View className="citations-area">
            {aggregatedCitations.map((c, i) => (
              <View key={i} className="citation-tag">
                <Text>
                  📚 [{i + 1}] {c.title}
                  {c.chapter ? ` · ${c.chapter}` : ""}
                  {c.sourceType ? ` · ${citationTypeLabelMap[c.sourceType] || c.sourceType}` : ""}
                  {c.count > 1 ? ` · 共${c.count}个片段` : ""}
                </Text>
              </View>
            ))}
          </View>
        )}

        {!isUser && !isLoading && !msg.isError && msg.id !== 1 && (
          <View
            className="chat-bubble-footer"
            style={{
              marginTop: "12px",
              paddingTop: "8px",
              borderTop: "1px solid rgba(0,0,0,0.05)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: "10px",
              color: "#aaa",
            }}
          >
            <View
              className="disclaimer"
              style={{ flex: 1, marginRight: "10px" }}
            >
              内容由 AI 总结生成，仅供医学参考。
              {msg.duration ? ` (耗时: ${msg.duration.toFixed(1)}s)` : ""}
            </View>
            <View
              className="copy-btn"
              style={{
                cursor: "pointer",
                padding: "2px 6px",
                backgroundColor: "rgba(0,0,0,0.04)",
                borderRadius: "4px",
                whiteSpace: "nowrap",
              }}
              onClick={() => {
                if (process.env.TARO_ENV === "h5") {
                  const input = document.createElement("textarea");
                  input.value = msg.text;
                  document.body.appendChild(input);
                  input.select();
                  try {
                    document.execCommand("copy");
                    Taro.showToast({ title: "已复制", icon: "success" });
                  } catch (err) {
                    Taro.showToast({ title: "复制失败", icon: "error" });
                  }
                  document.body.removeChild(input);
                } else {
                  Taro.setClipboardData({
                    data: msg.text,
                    success: () =>
                      Taro.showToast({ title: "已复制", icon: "success" }),
                  });
                }
              }}
            >
              复制
            </View>
          </View>
        )}
      </View>
    </View>
  );
}
