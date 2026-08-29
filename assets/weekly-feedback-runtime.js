(() => {
  let params;
  try {
    params = parseFormData();
  } catch (error) {
    renderDataError(error);
    console.error("周报反馈数据解析失败", error);
    return;
  }

  const state = {
    projects: params.projects.map((project) => ({ id: project.id, name: project.name })),
    satisfaction: params.satisfaction || "",
    dissatisfactionReasons: [...(params.dissatisfactionReasons || [])],
    feedback: params.feedback || "",
    submitted: Boolean(params.formDisabled),
    feedbackUser: null,
    identityPromise: null,
  };

  const elements = {
    card: document.querySelector("#feedbackCard"),
    form: document.querySelector("#feedbackForm"),
    icon: document.querySelector("#cardIcon"),
    title: document.querySelector("#cardTitle"),
    reportLink: document.querySelector("#reportLink"),
    reportLinkText: document.querySelector("#reportLinkText"),
    summary: document.querySelector("#weeklySummary"),
    period: document.querySelector("#reportPeriod"),
    customerName: document.querySelector("#customerName"),
    projectNames: document.querySelector("#projectNames"),
    satisfactionOptions: document.querySelector("#satisfactionOptions"),
    dissatisfactionReasons: document.querySelector("#dissatisfactionReasons"),
    reasonSummary: document.querySelector("#reasonSummary"),
    reasonOptions: document.querySelector("#reasonOptions"),
    feedbackInput: document.querySelector("#feedbackInput"),
    submitButton: document.querySelector("#submitButton"),
    submitMessage: document.querySelector("#submitMessage"),
  };

  function parseFormData() {
    const dataElement = document.querySelector("#weeklyFeedbackFormData");
    if (!dataElement) throw new Error("缺少 weeklyFeedbackFormData 数据块");

    let source;
    try {
      source = JSON.parse(dataElement.textContent);
    } catch (error) {
      throw new Error(`weeklyFeedbackFormData 不是合法 JSON：${error.message}`);
    }
    return validateFormData(source);
  }

  function validateFormData(source) {
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("表单数据必须是 JSON 对象");
    }
    if (source.schemaVersion !== 2) throw new Error("schemaVersion 必须为 2");

    [
      "iconUrl",
      "title",
      "reportUrl",
      "reportPeriod",
      "customer",
      "week",
      "collector",
      "reportTime",
      "submissionId",
    ].forEach((field) => {
      if (typeof source[field] !== "string" || !source[field].trim()) {
        throw new Error(`${field} 必须是非空字符串`);
      }
    });

    if (!Array.isArray(source.summaryMarkdown)) {
      throw new Error("summaryMarkdown 必须是字符串数组");
    }
    if (!source.summaryMarkdown.every((item) => typeof item === "string")) {
      throw new Error("summaryMarkdown 只能包含字符串");
    }
    if (!Array.isArray(source.projects) || source.projects.length === 0) {
      throw new Error("projects 必须是非空数组");
    }

    const projectIds = new Set();
    source.projects.forEach((project, index) => {
      if (!project || typeof project !== "object" || Array.isArray(project)) {
        throw new Error(`projects[${index}] 必须是对象`);
      }
      if (typeof project.id !== "string" || !project.id.trim()) {
        throw new Error(`projects[${index}].id 必须是非空字符串`);
      }
      if (projectIds.has(project.id)) throw new Error(`项目 id 重复：${project.id}`);
      projectIds.add(project.id);
      if (typeof project.name !== "string" || !project.name.trim()) {
        throw new Error(`projects[${index}].name 必须是非空字符串`);
      }
    });

    if (!Array.isArray(source.dissatisfactionOptions)) {
      throw new Error("dissatisfactionOptions 必须是字符串数组");
    }
    if (!source.dissatisfactionOptions.every((item) => typeof item === "string")) {
      throw new Error("dissatisfactionOptions 只能包含字符串");
    }
    if (
      source.satisfaction !== undefined &&
      !["", "满意", "不满意"].includes(source.satisfaction)
    ) {
      throw new Error("satisfaction 只能是满意或不满意");
    }
    if (
      source.dissatisfactionReasons !== undefined &&
      (!Array.isArray(source.dissatisfactionReasons) ||
        !source.dissatisfactionReasons.every((item) => typeof item === "string"))
    ) {
      throw new Error("dissatisfactionReasons 必须是字符串数组");
    }
    if (source.feedback !== undefined && typeof source.feedback !== "string") {
      throw new Error("feedback 必须是字符串");
    }
    if (source.callbackUrl !== undefined && typeof source.callbackUrl !== "string") {
      throw new Error("callbackUrl 必须是字符串");
    }
    if (source.formDisabled !== undefined && typeof source.formDisabled !== "boolean") {
      throw new Error("formDisabled 必须是布尔值");
    }

    return {
      reportLinkText: "查看完整周报",
      satisfaction: "",
      dissatisfactionReasons: [],
      feedback: "",
      callbackUrl: "",
      callbackHeaders: {},
      formDisabled: false,
      ...source,
    };
  }

  function renderDataError(error) {
    const card = document.querySelector("#feedbackCard");
    const content = document.createElement("section");
    const title = document.createElement("h1");
    const message = document.createElement("p");
    content.className = "data-error";
    title.className = "data-error__title";
    message.className = "data-error__message";
    title.textContent = "反馈表单无法加载";
    message.textContent = error?.message || "请检查 weeklyFeedbackFormData JSON 数据块";
    content.append(title, message);
    card.replaceChildren(content);
  }

  function safeHttpUrl(value) {
    try {
      const url = new URL(value, window.location.href);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
    } catch {
      return "#";
    }
  }

  function appendInlineMarkdown(parent, value) {
    String(value)
      .split(/(\*\*[^*]+\*\*)/g)
      .filter(Boolean)
      .forEach((fragment) => {
        if (fragment.startsWith("**") && fragment.endsWith("**")) {
          const strong = document.createElement("strong");
          strong.textContent = fragment.slice(2, -2);
          parent.append(strong);
        } else {
          parent.append(document.createTextNode(fragment));
        }
      });
  }

  function renderSummary() {
    elements.summary.replaceChildren();
    elements.summary.hidden = params.summaryMarkdown.length === 0;
    params.summaryMarkdown.forEach((line) => {
      const item = document.createElement("li");
      appendInlineMarkdown(item, line);
      elements.summary.append(item);
    });
  }

  function renderReadOnlyContext() {
    elements.customerName.textContent = params.customer;
    elements.projectNames.replaceChildren();
    state.projects.forEach((project) => {
      const tag = document.createElement("span");
      tag.className = "project-tag";
      tag.textContent = project.name;
      elements.projectNames.append(tag);
    });
  }

  function renderSatisfaction() {
    elements.satisfactionOptions.replaceChildren();
    ["满意", "不满意"].forEach((value) => {
      const label = document.createElement("label");
      label.className = "choice-option";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "satisfaction";
      input.value = value;
      input.checked = state.satisfaction === value;
      input.disabled = state.submitted;
      input.addEventListener("change", () => {
        state.satisfaction = value;
        if (value === "满意") state.dissatisfactionReasons = [];
        elements.satisfactionOptions.classList.remove("is-invalid");
        renderReasons();
      });
      const text = document.createElement("span");
      text.textContent = value;
      label.append(input, text);
      elements.satisfactionOptions.append(label);
    });
  }

  function selectedReasonText() {
    return state.dissatisfactionReasons.join("，");
  }

  function renderReasons() {
    const enabled = state.satisfaction === "不满意" && !state.submitted;
    const selectedText = selectedReasonText();
    elements.dissatisfactionReasons.hidden = state.satisfaction !== "不满意";
    elements.reasonSummary.textContent = selectedText || "选择不满意原因（可多选）";
    elements.reasonOptions.replaceChildren();

    params.dissatisfactionOptions.forEach((reason) => {
      const label = document.createElement("label");
      label.className = "reason-option";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = reason;
      checkbox.checked = state.dissatisfactionReasons.includes(reason);
      checkbox.disabled = !enabled;
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) {
          if (!state.dissatisfactionReasons.includes(reason)) {
            state.dissatisfactionReasons.push(reason);
          }
        } else {
          state.dissatisfactionReasons = state.dissatisfactionReasons.filter(
            (item) => item !== reason,
          );
        }
        elements.reasonSummary.textContent =
          selectedReasonText() || "选择不满意原因（可多选）";
      });
      const text = document.createElement("span");
      text.textContent = reason;
      label.append(checkbox, text);
      elements.reasonOptions.append(label);
    });

    if (!enabled) elements.dissatisfactionReasons.removeAttribute("open");
  }

  function normalizeFeedbackUser(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("钉钉返回的当前用户信息无效");
    }
    const userId = String(value.uid ?? "").trim();
    if (!userId) throw new Error("钉钉返回的当前用户信息缺少 uid");
    return {
      userId,
      name: String(value.name ?? "").trim(),
      avatar: String(value.avatar ?? "").trim(),
      corpId: String(value.corpId ?? "").trim(),
    };
  }

  async function loadFeedbackUser() {
    if (!window.DingTalkIdentity?.getCurrentUserInfo) {
      throw new Error("钉钉身份组件未加载");
    }
    const feedbackUser = normalizeFeedbackUser(
      await window.DingTalkIdentity.getCurrentUserInfo({}),
    );
    state.feedbackUser = feedbackUser;
    return feedbackUser;
  }

  function getFeedbackUser() {
    if (state.feedbackUser) return Promise.resolve(state.feedbackUser);
    state.identityPromise ||= loadFeedbackUser();
    return state.identityPromise;
  }

  function buildPayload(feedbackUser) {
    return {
      schemaVersion: 2,
      action: "submit_weekly_feedback",
      submissionId: params.submissionId,
      reportUrl: params.reportUrl,
      reportPeriod: params.reportPeriod,
      customer: params.customer,
      week: params.week,
      projects: state.projects.map((project) => project.name),
      satisfaction: state.satisfaction,
      dissatisfactionReasons: [...state.dissatisfactionReasons],
      feedback: state.feedback,
      collector: params.collector,
      reportTime: params.reportTime,
      feedbackUser,
      feedbackUserId: feedbackUser.userId,
      feedbackUserName: feedbackUser.name,
    };
  }

  function validate() {
    const valid = Boolean(state.satisfaction);
    elements.satisfactionOptions.classList.toggle("is-invalid", !valid);
    return valid;
  }

  function setSubmitted() {
    state.submitted = true;
    elements.card.classList.add("is-submitted");
    elements.submitButton.textContent = "已提交";
    elements.submitButton.disabled = true;
    elements.feedbackInput.disabled = true;
    renderSatisfaction();
    renderReasons();
  }

  async function submitFeedback(event) {
    event.preventDefault();
    elements.submitMessage.classList.remove("is-error");
    elements.submitMessage.textContent = "";
    state.feedback = elements.feedbackInput.value.trim();

    if (!validate()) {
      elements.submitMessage.classList.add("is-error");
      elements.submitMessage.textContent = "请选择本次服务是否满意";
      elements.satisfactionOptions.querySelector("input")?.focus();
      return;
    }

    elements.submitButton.disabled = true;
    elements.submitButton.textContent = "提交中…";

    try {
      const feedbackUser = await getFeedbackUser();
      const payload = buildPayload(feedbackUser);
      const response = await fetch(params.callbackUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(params.callbackHeaders || {}),
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(`提交失败（${response.status}）`);

      setSubmitted();
      elements.submitMessage.textContent = "反馈已提交，感谢您的确认";
    } catch (error) {
      elements.submitButton.disabled = false;
      elements.submitButton.textContent = "提交反馈";
      elements.submitMessage.classList.add("is-error");
      elements.submitMessage.textContent = error?.message || "提交失败，请稍后重试";
    }
  }

  function initialize() {
    elements.icon.src = params.iconUrl;
    elements.icon.alt = `${params.customer}图标`;
    elements.title.textContent = params.title;
    document.title = params.title;
    elements.period.textContent = params.reportPeriod;
    elements.reportLink.href = safeHttpUrl(params.reportUrl);
    elements.reportLinkText.textContent = params.reportLinkText;
    elements.feedbackInput.value = state.feedback;
    elements.feedbackInput.disabled = state.submitted;
    elements.submitButton.textContent = "提交反馈";
    elements.form.addEventListener("submit", submitFeedback);
    renderSummary();
    renderReadOnlyContext();
    renderSatisfaction();
    renderReasons();
    state.identityPromise = loadFeedbackUser();
    state.identityPromise.catch((error) => {
      console.error("周报反馈页获取当前用户失败", error);
    });
    if (state.submitted) setSubmitted();
  }

  initialize();
})();
