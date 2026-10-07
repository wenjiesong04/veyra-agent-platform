export function connectionFailureMessage(code: string, locale: "zh" | "en"): string {
  const zh = locale === "zh";
  const messages: Record<string, [string, string]> = {
    provider_console_url: ["填写的是账户管理网页，无法调用模型。请修正服务地址。", "An account webpage was entered. Correct the service address to call models."],
    runtime_endpoint_not_found: ["这个服务地址没有对应的模型接口。请修正服务地址或选择正确的服务商。", "No matching model endpoint exists at this address. Correct the address or choose the right Provider."],
    provider_endpoint_invalid: ["服务返回了网页而不是模型结果，请修正服务地址。", "The service returned a webpage instead of a model result. Correct the service address."],
    runtime_model_not_found: ["服务商没有找到这个模型。请从模型列表选择，或核对服务商提供的模型名称。", "The Provider could not find this model. Select one from its list or check the supplied model name."],
    runtime_unauthorized: ["密钥验证未通过，请重新粘贴完整密钥，并确认密钥与服务商、地区相匹配。", "The key was rejected. Paste the complete key and check that its Provider and region match."],
    runtime_forbidden: ["这个密钥没有调用模型的权限，请在服务商账户中开通权限或更换密钥。", "This key lacks permission to call the model. Enable access in the Provider account or replace the key."],
    runtime_quota_exhausted: ["服务商余额或可用额度不足，请在服务商账户中检查后重试。", "The Provider balance or quota is exhausted. Check your account before retrying."],
    runtime_rate_limited: ["服务商暂时限制了请求次数，请稍后重试。", "The Provider is limiting requests. Try again later."],
    runtime_parameter_invalid: ["服务商不接受当前测试参数。请检查接口格式，或使用服务商推荐的模型设置。", "The Provider rejected the test parameters. Check the API format or recommended model settings."],
    runtime_request_invalid: ["服务商拒绝了测试请求。请先检查服务地址和模型名称；如果仍失败，可展开“检查详情”查看原因。", "The Provider rejected the test request. Check the service address and model name, then inspect the check details."],
    runtime_timeout: ["服务响应超时，可能仍在处理请求。请稍后检查状态再决定是否重试。", "The service timed out and may still be processing. Check its status before retrying."],
    runtime_unavailable: ["暂时无法连接到服务，请检查网络或服务地址后重试。", "The service could not be reached. Check the network and address, then retry."],
    runtime_provider_error: ["服务商暂时出现问题，请稍后重试或检查服务状态。", "The Provider encountered an error. Check its status or try again later."],
    runtime_invalid_response: ["返回内容不是可识别的模型结果。请检查服务地址；该接口格式也可能尚未兼容。", "The response was not a recognized model result. Check the address; the API format may be unsupported."],
    model_connection_endpoint_changed: ["服务地址已更改，请重新检查此模型是否可用。", "The service address changed. Check whether this model works again."],
    model_connection_disabled: ["此 API 已停用，请先在连接设置中启用。", "This API is disabled. Enable it in connection settings first."],
    image_generation_unsupported: ["当前接口没有返回图片生成能力，请选择支持生成图片的模型或服务。", "This API does not expose image generation. Choose an image-capable model or service."],
  };
  const aliases: Record<string, string> = { runtime_endpoint_invalid: "provider_endpoint_invalid", runtime_permission_denied: "runtime_forbidden", runtime_model_unavailable: "runtime_model_not_found", runtime_parameters_unsupported: "runtime_parameter_invalid", runtime_insufficient_balance: "runtime_quota_exhausted" };
  return messages[aliases[code] ?? code]?.[zh ? 0 : 1] ?? (zh ? "这次测试未完成，请检查连接设置后重试。" : "This test did not finish. Check connection settings and retry.");
}
