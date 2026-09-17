module github.com/hanzoai/benchmarks/framework/zip

go 1.27.1

// Published deps only — the zero-alloc codec is merged and tagged, so the bench
// is reproducible off tags without any local working-copy replace. Versions live
// in the require block below, not in this comment.
require (
	github.com/bytedance/sonic v1.15.2
	github.com/goccy/go-json v0.10.6
	github.com/valyala/fasthttp v1.72.0
	github.com/zap-proto/go v1.3.0
	github.com/zap-proto/http v0.3.1
	github.com/zap-proto/zip v1.17.2
)

require (
	github.com/andybalholm/brotli v1.2.1 // indirect
	github.com/bytedance/gopkg v0.1.3 // indirect
	github.com/bytedance/sonic/loader v0.5.1 // indirect
	github.com/cloudwego/base64x v0.1.6 // indirect
	github.com/dlclark/regexp2/v2 v2.2.1 // indirect
	github.com/dop251/goja v0.0.0-20260607120635-348e6bea910d // indirect
	github.com/evanw/esbuild v0.28.1 // indirect
	github.com/go-sourcemap/sourcemap v2.1.3+incompatible // indirect
	github.com/gofiber/schema v1.7.1 // indirect
	github.com/gofiber/utils/v2 v2.0.4 // indirect
	github.com/google/pprof v0.0.0-20230207041349-798e818bf904 // indirect
	github.com/google/uuid v1.6.0 // indirect
	github.com/klauspost/compress v1.18.6 // indirect
	github.com/klauspost/cpuid/v2 v2.2.9 // indirect
	github.com/luxfi/log v1.4.3 // indirect
	github.com/mattn/go-colorable v0.1.14 // indirect
	github.com/mattn/go-isatty v0.0.21 // indirect
	github.com/philhofer/fwd v1.2.0 // indirect
	github.com/tinylib/msgp v1.6.4 // indirect
	github.com/twitchyliquid64/golang-asm v0.15.1 // indirect
	github.com/valyala/bytebufferpool v1.0.0 // indirect
	github.com/zap-proto/fiber/v3 v3.2.1 // indirect
	golang.org/x/arch v0.0.0-20210923205945-b76863e36670 // indirect
	golang.org/x/crypto v0.53.0 // indirect
	golang.org/x/net v0.56.0 // indirect
	golang.org/x/sys v0.46.0 // indirect
	golang.org/x/text v0.38.0 // indirect
	gopkg.in/natefinch/lumberjack.v2 v2.2.1 // indirect
)
