package com.ssafy.witw;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class WitwApplication {

	public static void main(String[] args) {
		SpringApplication.run(WitwApplication.class, args);
	}

}
