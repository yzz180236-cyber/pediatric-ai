import React, { useEffect } from "react";
import { View, Image } from "@tarojs/components";
import { Button, Input } from "@nutui/nutui-react-taro";
import { Trash, Photograph, Close } from "@nutui/icons-react-taro";
import "./index.scss";

interface ChatInputBarProps {
  value: string;
  loading: boolean;
  imageUrl?: string;
  onChange: (val: string) => void;
  onSend: () => void;
  onClear: () => void;
  onUploadImage: () => void;
  onClearImage: () => void;
  onPasteFile: (file: File) => void;
  onStop?: () => void;
}

export function ChatInputBar({
  value,
  loading,
  imageUrl,
  onChange,
  onSend,
  onStop,
  onClear,
  onUploadImage,
  onClearImage,
  onPasteFile,
}: ChatInputBarProps) {
  useEffect(() => {
    // 支持 Web 端原生的剪贴板图片粘贴
    const handlePaste = (e: any) => {
      try {
        const clipboardData =
          e.clipboardData ||
          e.originalEvent?.clipboardData ||
          (window as any).clipboardData;
        if (!clipboardData) return;

        let blob: File | null = null;

        // 1. 优先尝试从 files 获取 (支持从本地文件夹直接复制文件粘贴)
        if (clipboardData.files && clipboardData.files.length > 0) {
          for (let i = 0; i < clipboardData.files.length; i++) {
            if (clipboardData.files[i].type.indexOf("image") !== -1) {
              blob = clipboardData.files[i];
              break;
            }
          }
        }

        // 2. 如果 files 没抓到，退化使用 items 获取 (支持从截图工具、网页等截取粘贴)
        if (!blob && clipboardData.items) {
          for (let i = 0; i < clipboardData.items.length; i++) {
            if (clipboardData.items[i].type.indexOf("image") !== -1) {
              blob = clipboardData.items[i].getAsFile();
              break;
            }
          }
        }

        if (blob) {
          onPasteFile(blob);
          e.preventDefault();
          e.stopPropagation(); // 防止继续触发组件库内部的报错
        }
      } catch (err) {
        console.error("解析粘贴图片失败:", err);
      }
    };

    window.addEventListener("paste", handlePaste, true);
    return () => window.removeEventListener("paste", handlePaste, true);
  }, [onPasteFile]);

  return (
    <View className="chat-input-wrapper">
      {imageUrl && (
        <View className="image-preview-area">
          <Image src={imageUrl} className="preview-img" mode="aspectFill" />
          <View className="close-btn" onClick={onClearImage}>
            <Close size={12} color="#fff" />
          </View>
        </View>
      )}
      <View className="chat-input-bar">
        <View className="action-icons">
          <Trash size={20} className="action-icon" onClick={onClear} />
          <Photograph
            size={20}
            className="action-icon"
            onClick={onUploadImage}
          />
        </View>
        <Input
          value={value}
          onChange={onChange}
          placeholder="请输入症状"
          className="chat-input"
          onConfirm={onSend}
        />
        {loading ? (
          <View className="chat-stop-btn-wrapper" onClick={onStop}>
            <View className="loading-ring"></View>
            <View className="stop-square"></View>
          </View>
        ) : (
          <Button type="primary" className="chat-send-btn" onClick={onSend}>
            发送
          </Button>
        )}
      </View>
    </View>
  );
}
