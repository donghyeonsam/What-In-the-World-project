package com.ssafy.witw;

import com.ssafy.witw.support.TestContainerSupport;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisGmsService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
@ActiveProfiles("test")
class WitwApplicationTests extends TestContainerSupport {

	@MockitoBean
	private IssueCountryAnalysisGmsService gmsService;

	@Test
	void contextLoads() {
	}

}
