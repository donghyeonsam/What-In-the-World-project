package com.ssafy.witw.infra;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.IntegerSchema;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.responses.ApiResponse;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration(proxyBeanMethods = false)
public class OpenApiConfig {
    @Bean
    OpenAPI openAPI() {
        Schema<?> errorSchema = new ObjectSchema()
                .addProperty("status", new IntegerSchema().example(400))
                .addProperty("code", new StringSchema().example("CO01"))
                .addProperty("message", new StringSchema().example("유효하지 않은 입력 값입니다."))
                .required(List.of("status", "code", "message"));
        return new OpenAPI()
                .info(new Info().title("WITW 조회 API").version("v1")
                        .description("모든 조회 API는 로그인 없이 호출할 수 있습니다. 성공 응답은 status, message, data를, 오류 응답은 status, code, message를 반환합니다."))
                .components(new Components().addSchemas("ApiError", errorSchema));
    }

    @Bean
    OpenApiCustomizer commonErrorResponses() {
        return openApi -> openApi.getPaths().values().forEach(path -> path.readOperations().forEach(operation -> {
            operation.getResponses().addApiResponse("400", errorResponse("잘못된 ID, 국가 코드 또는 조회 개수"));
            operation.getResponses().addApiResponse("404", errorResponse("조회 대상 또는 요청 경로가 없음"));
            operation.getResponses().addApiResponse("405", errorResponse("지원하지 않는 HTTP 메서드"));
            operation.getResponses().addApiResponse("500", errorResponse("서버 내부 오류"));
        }));
    }

    private ApiResponse errorResponse(String description) {
        return new ApiResponse().description(description).content(new Content()
                .addMediaType("application/json", new MediaType()
                        .schema(new Schema<>().$ref("#/components/schemas/ApiError"))));
    }
}
