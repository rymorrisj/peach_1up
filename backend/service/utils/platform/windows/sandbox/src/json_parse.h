#pragma once
// Minimal JSON parser scoped to LaunchConfig. No error recovery.
// Throws std::runtime_error on malformed input or missing fields.
#include <cctype>
#include <cstdlib>
#include <cstring>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

struct JVal {
    enum class T { Obj, Arr, Str, Num, Bool, Null } tag = T::Null;
    std::map<std::string, JVal> obj;
    std::vector<JVal>           arr;
    std::string                 str;
    double                      num = 0;
    bool                        b   = false;

    const JVal& at(const std::string& k) const {
        auto it = obj.find(k);
        if (it == obj.end()) throw std::runtime_error("missing field: " + k);
        return it->second;
    }
    std::string value(const std::string& k, const std::string& def) const {
        auto it = obj.find(k);
        return (it != obj.end() && it->second.tag == T::Str) ? it->second.str : def;
    }
    bool value(const std::string& k, bool def) const {
        auto it = obj.find(k);
        return (it != obj.end() && it->second.tag == T::Bool) ? it->second.b : def;
    }
    template<class V> V get() const;
};

template<> inline std::string        JVal::get<std::string>()           const {
    if (tag != T::Str)  throw std::runtime_error("expected string");
    return str;
}
template<> inline unsigned long      JVal::get<unsigned long>()         const {
    if (tag != T::Num)  throw std::runtime_error("expected number");
    return static_cast<unsigned long>(num);
}
template<> inline unsigned long long JVal::get<unsigned long long>()    const {
    if (tag != T::Num)  throw std::runtime_error("expected number");
    return static_cast<unsigned long long>(num);
}
template<> inline bool               JVal::get<bool>()                  const {
    if (tag != T::Bool) throw std::runtime_error("expected bool");
    return b;
}

namespace json_detail {
struct Parser {
    const char* p;
    const char* end;
    explicit Parser(const std::string& s) : p(s.data()), end(s.data() + s.size()) {}

    void ws()  { while (p < end && std::isspace((unsigned char)*p)) ++p; }
    char peek(){ ws(); return p < end ? *p : '\0'; }
    void eat(char c) {
        ws();
        if (p >= end || *p != c)
            throw std::runtime_error(std::string("expected '") + c + '\'');
        ++p;
    }
    std::string parse_str() {
        eat('"');
        std::string s;
        while (p < end && *p != '"') {
            if (*p == '\\') {
                if (++p >= end) throw std::runtime_error("truncated escape");
                switch (*p) {
                    case '"':  s += '"';  break;
                    case '\\': s += '\\'; break;
                    case '/':  s += '/';  break;
                    case 'n':  s += '\n'; break;
                    case 'r':  s += '\r'; break;
                    case 't':  s += '\t'; break;
                    default:   s += *p;   break;
                }
            } else {
                s += *p;
            }
            ++p;
        }
        eat('"');
        return s;
    }
    JVal parse_val();
    JVal parse_obj() {
        eat('{');
        JVal v; v.tag = JVal::T::Obj;
        if (peek() == '}') { ++p; return v; }
        for (;;) {
            std::string k = parse_str();
            eat(':');
            v.obj[k] = parse_val();
            if (peek() == '}') { ++p; break; }
            eat(',');
        }
        return v;
    }
    JVal parse_arr() {
        eat('[');
        JVal v; v.tag = JVal::T::Arr;
        if (peek() == ']') { ++p; return v; }
        for (;;) {
            v.arr.push_back(parse_val());
            if (peek() == ']') { ++p; break; }
            eat(',');
        }
        return v;
    }
};

inline JVal Parser::parse_val() {
    char c = peek();
    if (c == '{') return parse_obj();
    if (c == '[') return parse_arr();
    if (c == '"') { JVal v; v.tag = JVal::T::Str; v.str = parse_str(); return v; }
    if (c == 't' || c == 'f') {
        bool bv = (c == 't');
        const char* lit = bv ? "true" : "false";
        size_t      len = bv ? 4      : 5;
        if (std::strncmp(p, lit, len) != 0) throw std::runtime_error("invalid literal");
        p += len;
        JVal v; v.tag = JVal::T::Bool; v.b = bv;
        return v;
    }
    if (c == 'n') {
        if (std::strncmp(p, "null", 4) != 0) throw std::runtime_error("invalid literal");
        p += 4;
        JVal v; v.tag = JVal::T::Null;
        return v;
    }
    char* ep;
    double d = std::strtod(p, &ep);
    if (ep == p) throw std::runtime_error("expected JSON value");
    p = ep;
    JVal v; v.tag = JVal::T::Num; v.num = d;
    return v;
}
} // namespace json_detail

inline JVal json_parse(const std::string& s) {
    return json_detail::Parser(s).parse_val();
}

// Flat JSON object builder for output.
class JsonOut {
    std::string buf_;
    bool        first_ = true;
    static std::string quote(const std::string& s) {
        std::string r = "\"";
        for (char c : s) {
            if      (c == '"')  r += "\\\"";
            else if (c == '\\') r += "\\\\";
            else if (c == '\n') r += "\\n";
            else if (c == '\r') r += "\\r";
            else                r += c;
        }
        return r + '"';
    }
    void sep() { if (!first_) buf_ += ','; first_ = false; }
public:
    JsonOut() { buf_ = '{'; }
    JsonOut& set(const std::string& k, const std::string& v)
        { sep(); buf_ += quote(k) + ':' + quote(v); return *this; }
    JsonOut& set(const std::string& k, long long v)
        { sep(); buf_ += quote(k) + ':' + std::to_string(v); return *this; }
    JsonOut& set(const std::string& k, bool v)
        { sep(); buf_ += quote(k) + ':' + (v ? "true" : "false"); return *this; }
    std::string dump() const { return buf_ + '}'; }
};
