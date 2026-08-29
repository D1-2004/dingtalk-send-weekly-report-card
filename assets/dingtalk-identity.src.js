import "@ali/dingtalk-jsapi/entry/union";
import getCurrentUserInfo from "@ali/dingtalk-jsapi/api/internal/user/getCurrentUserInfo";
import { getENV } from "@ali/dingtalk-jsapi/lib/env";

window.DingTalkIdentity = Object.freeze({
  getCurrentUserInfo,
  getEnvironment: getENV,
});
