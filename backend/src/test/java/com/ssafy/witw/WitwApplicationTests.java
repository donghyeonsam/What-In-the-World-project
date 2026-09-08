package com.ssafy.witw;

import com.ssafy.witw.support.TestContainerSupport;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class WitwApplicationTests extends TestContainerSupport {

	@Test
	void contextLoads() {
	}

}
